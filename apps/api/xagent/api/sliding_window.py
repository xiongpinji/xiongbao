"""滑动窗口限流：精确的请求频率控制。

功能：
- 滑动时间窗口计数
- 按租户/用户/IP 分桶
- 支持多粒度窗口（秒/分/时）
- 限流响应头

用法：
    from xagent.api.sliding_window import SlidingWindowMiddleware

    app.add_middleware(SlidingWindowMiddleware, max_requests=100, window_s=60)
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.sliding_window")


@dataclass
class WindowConfig:
    """窗口配置。"""

    max_requests: int = 100
    window_s: float = 60.0


class SlidingWindowCounter:
    """滑动窗口计数器。"""

    def __init__(self, max_requests: int, window_s: float):
        self._max = max_requests
        self._window_s = window_s
        self._requests: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> tuple[bool, int, float]:
        """检查是否允许请求。

        Returns:
            (allowed, remaining, retry_after_s)
        """
        now = time.time()
        cutoff = now - self._window_s

        # 清理过期记录
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]
        timestamps = self._requests[key]

        if len(timestamps) >= self._max:
            # 计算最早记录过期时间
            retry_after = timestamps[0] + self._window_s - now
            return False, 0, max(0, retry_after)

        timestamps.append(now)
        remaining = self._max - len(timestamps)
        return True, remaining, 0

    def reset(self, key: str) -> None:
        """重置指定 key。"""
        self._requests.pop(key, None)

    def cleanup(self) -> int:
        """清理所有过期记录，返回清理的 key 数。"""
        now = time.time()
        cutoff = now - self._window_s
        expired_keys = []
        for key, timestamps in self._requests.items():
            self._requests[key] = [t for t in timestamps if t > cutoff]
            if not self._requests[key]:
                expired_keys.append(key)
        for key in expired_keys:
            del self._requests[key]
        return len(expired_keys)


class SlidingWindowMiddleware(BaseHTTPMiddleware):
    """滑动窗口限流中间件。"""

    def __init__(
        self,
        app,
        max_requests: int = 100,
        window_s: float = 60.0,
        key_fn: str = "ip",  # ip | tenant | user
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.counter = SlidingWindowCounter(max_requests, window_s)
        self.key_fn = key_fn
        self.exclude_prefixes = exclude_prefixes or ["/health", "/ws"]
        self._last_cleanup = time.time()

    def _extract_key(self, request: Request) -> str:
        """提取限流 key。"""
        if self.key_fn == "tenant":
            return request.headers.get("x-tenant-id", "anonymous")
        if self.key_fn == "user":
            return request.headers.get("x-user-id", "anonymous")
        # 默认 IP
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        # 定期清理
        now = time.time()
        if now - self._last_cleanup > 300:
            self.counter.cleanup()
            self._last_cleanup = now

        key = self._extract_key(request)
        allowed, remaining, retry_after = self.counter.allow(key)

        if not allowed:
            logger.warning("rate limited: key=%s path=%s", key, path)
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "retry_after_s": round(retry_after, 1)},
                headers={
                    "Retry-After": str(int(retry_after) + 1),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
