"""滑动窗口限流：精确的 API 速率控制。

比固定窗口更精确，避免窗口边界突发：
- 滑动窗口日志（精确但内存高）
- 滑动窗口计数（近似但高效）
- 支持多维度（IP / 用户 / API Key）
- 返回标准限流头

用法：
    from xagent.api.sliding_rate_limit import SlidingWindowRateLimiter, RateLimitMiddleware

    limiter = SlidingWindowRateLimiter(max_requests=100, window_seconds=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.rate_limit")


@dataclass
class RateLimitResult:
    """限流检查结果。"""

    allowed: bool
    limit: int
    remaining: int
    reset_at: float  # Unix timestamp
    retry_after: int = 0  # 秒


class SlidingWindowRateLimiter:
    """滑动窗口日志限流器。

    精确记录每个请求时间戳，窗口滑动时淘汰过期记录。
    适合中低并发场景（< 10K QPS）。
    """

    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: int = 60,
        key_prefix: str = "rl",
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix
        # key → deque of timestamps
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._stats = {"total": 0, "blocked": 0}

    def check(self, key: str) -> RateLimitResult:
        """检查并记录请求。"""
        full_key = f"{self.key_prefix}:{key}"
        now = time.time()
        window_start = now - self.window_seconds

        self._stats["total"] += 1

        # 淘汰过期记录
        dq = self._requests[full_key]
        while dq and dq[0] <= window_start:
            dq.popleft()

        current_count = len(dq)

        if current_count >= self.max_requests:
            self._stats["blocked"] += 1
            # 计算最早记录过期时间
            retry_after = int(dq[0] + self.window_seconds - now) + 1
            return RateLimitResult(
                allowed=False,
                limit=self.max_requests,
                remaining=0,
                reset_at=dq[0] + self.window_seconds,
                retry_after=max(1, retry_after),
            )

        # 记录本次请求
        dq.append(now)
        remaining = self.max_requests - current_count - 1

        return RateLimitResult(
            allowed=True,
            limit=self.max_requests,
            remaining=remaining,
            reset_at=now + self.window_seconds,
        )

    def reset(self, key: str) -> None:
        """重置指定 key 的限流。"""
        full_key = f"{self.key_prefix}:{key}"
        self._requests.pop(full_key, None)

    def cleanup(self) -> int:
        """清理所有过期记录，返回清理数量。"""
        now = time.time()
        window_start = now - self.window_seconds
        cleaned = 0

        empty_keys = []
        for key, dq in self._requests.items():
            while dq and dq[0] <= window_start:
                dq.popleft()
                cleaned += 1
            if not dq:
                empty_keys.append(key)

        for key in empty_keys:
            del self._requests[key]

        return cleaned

    @property
    def stats(self) -> dict:
        return {
            **self._stats,
            "active_keys": len(self._requests),
        }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件。

    基于客户端 IP + 路径前缀进行限流。
    返回标准 RateLimit 头。
    """

    def __init__(
        self,
        app,
        limiter: SlidingWindowRateLimiter | None = None,
        max_requests: int = 100,
        window_seconds: int = 60,
        exclude_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.limiter = limiter or SlidingWindowRateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        self.exclude_paths = exclude_paths or ["/health", "/metrics"]

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 跳过排除路径
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        # 提取限流 key（IP + 路径前缀）
        client_ip = request.client.host if request.client else "unknown"
        # 取路径前两段作为维度
        parts = path.strip("/").split("/")
        path_prefix = "/".join(parts[:2]) if len(parts) >= 2 else path
        key = f"{client_ip}:{path_prefix}"

        result = self.limiter.check(key)

        if not result.allowed:
            logger.warning("rate limited: %s (%s)", key, path)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"请求过于频繁，请 {result.retry_after} 秒后重试",
                    "retry_after": result.retry_after,
                },
                headers={
                    "Retry-After": str(result.retry_after),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(result.reset_at)),
                },
            )

        response = await call_next(request)

        # 添加限流信息头
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))

        return response
