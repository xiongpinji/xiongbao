"""性能优化：响应时间中间件 + 内存缓存 + 请求限流。

- TimingMiddleware: 记录每个请求的 P50/P95/P99 响应时间
- LRUCache: 轻量内存缓存（API 结果 / 向量检索）
- RateLimiter: 滑动窗口限流
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger(__name__)


# ─── 响应时间追踪 ──────────────────────────────────────────


class TimingMiddleware(BaseHTTPMiddleware):
    """记录请求耗时到响应头 + 结构化日志。"""

    def __init__(self, app: Any, *, slow_threshold_ms: float = 500.0) -> None:
        super().__init__(app)
        self.slow_threshold_ms = slow_threshold_ms
        self._latencies: list[float] = []

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"
        self._latencies.append(elapsed_ms)
        # 保留最近 1000 条
        if len(self._latencies) > 1000:
            self._latencies = self._latencies[-500:]

        if elapsed_ms > self.slow_threshold_ms:
            logger.warning(
                "slow_request",
                path=request.url.path,
                method=request.method,
                elapsed_ms=round(elapsed_ms, 1),
            )
        return response

    def get_percentiles(self) -> dict[str, float]:
        """返回 P50/P95/P99 响应时间 (ms)。"""
        if not self._latencies:
            return {"p50": 0, "p95": 0, "p99": 0, "count": 0}
        sorted_lat = sorted(self._latencies)
        n = len(sorted_lat)
        return {
            "p50": round(sorted_lat[int(n * 0.5)], 1),
            "p95": round(sorted_lat[min(int(n * 0.95), n - 1)], 1),
            "p99": round(sorted_lat[min(int(n * 0.99), n - 1)], 1),
            "count": n,
        }


# ─── LRU 内存缓存 ──────────────────────────────────────────


class LRUCache:
    """线程安全的 LRU 缓存（带 TTL）。"""

    def __init__(self, max_size: int = 256, ttl_seconds: float = 300.0) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        if key in self._store:
            ts, value = self._store[key]
            if time.time() - ts < self._ttl:
                self._store.move_to_end(key)
                self._hits += 1
                return value
            del self._store[key]
        self._misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.time(), value)
        if len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._store),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0,
        }


# 全局缓存实例
_api_cache = LRUCache(max_size=512, ttl_seconds=120)
_search_cache = LRUCache(max_size=128, ttl_seconds=60)


def get_api_cache() -> LRUCache:
    return _api_cache


def get_search_cache() -> LRUCache:
    return _search_cache


# ─── 滑动窗口限流 ──────────────────────────────────────────


class RateLimiter:
    """简单滑动窗口限流器（内存级）。"""

    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self._window
        if key not in self._requests:
            self._requests[key] = []
        # 清理过期
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if len(self._requests[key]) >= self._max:
            return False
        self._requests[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        now = time.time()
        cutoff = now - self._window
        reqs = [t for t in self._requests.get(key, []) if t > cutoff]
        return max(0, self._max - len(reqs))


_rate_limiter = RateLimiter(max_requests=200, window_seconds=60)


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter
