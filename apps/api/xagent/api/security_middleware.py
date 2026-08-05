"""安全中间件：限流（Redis 分布式 / 进程内降级）+ 安全响应头。

限流：Redis 可用时用原子 Lua 脚本做滑动窗口（多实例一致）；否则降级进程内。
健康探针/metrics 豁免。超限 429 + Retry-After。
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.settings import get_settings

# Redis 原子滑动窗口 Lua：ZREMRANGEBYSCORE + ZADD + ZCARD
_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= max then
  return 0
end
redis.call('ZADD', key, now, now .. '-' .. math.random())
redis.call('EXPIRE', key, window)
return 1
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """滑动窗口限流。Redis 可用 -> 分布式；否则进程内。"""

    # 默认豁免前缀（健康探针/metrics）；可由 exempt_paths 参数覆盖
    DEFAULT_EXEMPT = ("/health", "/ready", "/metrics")

    def __init__(self, app, max_requests: int = 120, window_seconds: int = 60,
                 exempt_paths: list[str] | tuple[str, ...] | None = None) -> None:
        super().__init__(app)
        self._max = max_requests
        self._window = window_seconds
        self._exempt = (
            tuple(exempt_paths) if exempt_paths is not None else self.DEFAULT_EXEMPT
        )
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._redis = None
        self._lua_sha: str | None = None

    def _get_redis(self):
        """惰性获取 Redis 原生客户端（非我们的 Cache 抽象）。"""
        if self._redis is not None:
            return self._redis
        settings = get_settings()
        if not settings.cache.redis_url:
            return None
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(settings.cache.redis_url, decode_responses=True)
            return self._redis
        except Exception:
            return None

    async def dispatch(self, request: Request, call_next) -> Response:
        if any(request.url.path.startswith(p) for p in self._exempt):
            return await call_next(request)

        key = f"ratelimit:{request.client.host if request.client else 'anon'}"
        allowed = await self._check(key)
        if not allowed:
            return JSONResponse(
                {"detail": "请求过于频繁，请稍后再试"},
                status_code=429,
                headers={"Retry-After": str(self._window)},
            )
        return await call_next(request)

    async def _check(self, key: str) -> bool:
        redis = self._get_redis()
        if redis is not None:
            return await self._check_redis(redis, key)
        return self._check_local(key)

    async def _check_redis(self, redis, key: str) -> bool:
        now = int(time.time() * 1000)
        try:
            if self._lua_sha is None:
                self._lua_sha = await redis.script_load(_LUA)
            result = await redis.evalsha(
                self._lua_sha, 1, key, now, self._window * 1000, self._max
            )
            return int(result) == 1
        except Exception:
            # Redis 故障降级到进程内
            return self._check_local(key)

    def _check_local(self, key: str) -> bool:
        now = time.time()
        bucket = self._buckets[key]
        while bucket and now - bucket[0] > self._window:
            bucket.popleft()
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """注入安全响应头。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        settings = get_settings()
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
