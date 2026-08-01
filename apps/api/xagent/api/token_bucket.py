"""令牌桶限流：平滑流量控制。

功能：
- 经典令牌桶算法（突发 + 稳态）
- 按客户端/路径独立桶
- 异步安全（asyncio.Lock）
- 桶状态查询

用法：
    from xagent.api.token_bucket import TokenBucketLimiter

    limiter = TokenBucketLimiter(rate=10, burst=20)
    allowed = await limiter.acquire("client_123")
    # 或中间件模式：
    app.add_middleware(TokenBucketMiddleware, rate=100, burst=200)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.token_bucket")


@dataclass
class Bucket:
    """单个令牌桶。"""

    tokens: float
    last_refill: float = field(default_factory=time.monotonic)


class TokenBucketLimiter:
    """令牌桶限流器。"""

    def __init__(self, rate: float = 10.0, burst: int = 20):
        """
        Args:
            rate: 每秒补充令牌数
            burst: 桶容量（最大突发）
        """
        self.rate = rate
        self.burst = burst
        self._buckets: dict[str, Bucket] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str, tokens: float = 1.0) -> bool:
        """尝试获取令牌。"""
        async with self._lock:
            bucket = self._buckets.get(key)
            now = time.monotonic()

            if bucket is None:
                bucket = Bucket(tokens=float(self.burst))
                self._buckets[key] = bucket

            # 补充令牌
            elapsed = now - bucket.last_refill
            bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate)
            bucket.last_refill = now

            # 消费
            if bucket.tokens >= tokens:
                bucket.tokens -= tokens
                return True
            return False

    async def remaining(self, key: str) -> float:
        """查询剩余令牌。"""
        async with self._lock:
            bucket = self._buckets.get(key)
            if not bucket:
                return float(self.burst)
            elapsed = time.monotonic() - bucket.last_refill
            return min(self.burst, bucket.tokens + elapsed * self.rate)

    def cleanup(self, max_age: float = 300.0) -> int:
        """清理过期桶。"""
        now = time.monotonic()
        expired = [
            k for k, b in self._buckets.items()
            if now - b.last_refill > max_age
        ]
        for k in expired:
            del self._buckets[k]
        return len(expired)


class TokenBucketMiddleware(BaseHTTPMiddleware):
    """令牌桶限流中间件。"""

    def __init__(
        self,
        app,
        rate: float = 100.0,
        burst: int = 200,
        key_fn=None,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.limiter = TokenBucketLimiter(rate=rate, burst=burst)
        self.key_fn = key_fn or self._default_key
        self.exclude_prefixes = exclude_prefixes or ["/health", "/ws"]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        key = self.key_fn(request)
        allowed = await self.limiter.acquire(key)

        if not allowed:
            remaining = await self.limiter.remaining(key)
            logger.warning("token bucket exhausted: %s %s", key, path)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "请求过于频繁，请稍后重试",
                    "retry_after": round(1.0 / self.limiter.rate, 2),
                },
                headers={"Retry-After": str(int(1.0 / self.limiter.rate) + 1)},
            )

        response = await call_next(request)
        return response

    @staticmethod
    def _default_key(request: Request) -> str:
        """默认按 IP 限流。"""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"


# 全局实例
token_limiter = TokenBucketLimiter(rate=50, burst=100)
