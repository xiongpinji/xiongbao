"""幂等性保障：防止重复提交。

功能：
- Idempotency-Key 请求头
- 结果缓存（相同 key 返回缓存响应）
- 过期清理
- 并发去重（同 key 只执行一次）

用法：
    from xagent.api.idempotency import IdempotencyMiddleware

    app.add_middleware(IdempotencyMiddleware, ttl_s=3600)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, cast

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.idempotency")


@dataclass
class CachedResponse:
    """缓存的响应。"""

    status_code: int
    body: bytes
    headers: dict[str, str]
    created_at: float = field(default_factory=time.time)


class IdempotencyStore:
    """幂等性存储。"""

    def __init__(self, ttl_s: float = 3600.0, max_entries: int = 10000):
        self._store: dict[str, CachedResponse] = {}
        self._in_progress: dict[str, asyncio.Event] = {}
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> CachedResponse | None:
        """获取缓存响应。"""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        # 检查过期
        if time.time() - entry.created_at > self._ttl_s:
            del self._store[key]
            self._misses += 1
            return None

        self._hits += 1
        return entry

    def set(self, key: str, response: CachedResponse) -> None:
        """缓存响应。"""
        # 容量限制
        if len(self._store) >= self._max_entries:
            self._evict()
        self._store[key] = response

    def is_in_progress(self, key: str) -> bool:
        """是否有同 key 请求正在处理。"""
        return key in self._in_progress

    def mark_progress(self, key: str) -> asyncio.Event:
        """标记处理中。"""
        event = asyncio.Event()
        self._in_progress[key] = event
        return event

    def complete_progress(self, key: str) -> None:
        """完成处理。"""
        event = self._in_progress.pop(key, None)
        if event:
            event.set()

    def _evict(self) -> None:
        """淘汰过期/最旧条目。"""
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v.created_at > self._ttl_s]
        for k in expired:
            del self._store[k]

        # 仍满则删除最旧
        if len(self._store) >= self._max_entries:
            sorted_keys = sorted(self._store, key=lambda k: self._store[k].created_at)
            for k in sorted_keys[: len(sorted_keys) // 4]:
                del self._store[k]

    def get_stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._store),
            "in_progress": len(self._in_progress),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(1, self._hits + self._misses), 3),
        }


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """幂等性中间件。"""

    IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH"}
    HEADER = "idempotency-key"

    def __init__(self, app, ttl_s: float = 3600.0, max_entries: int = 10000):
        super().__init__(app)
        self.store = IdempotencyStore(ttl_s=ttl_s, max_entries=max_entries)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 仅对写操作生效
        if request.method not in self.IDEMPOTENT_METHODS:
            return await call_next(request)

        key = request.headers.get(self.HEADER)
        if not key:
            return await call_next(request)

        # 检查缓存
        cached = self.store.get(key)
        if cached:
            logger.debug("idempotency hit: key=%s", key)
            return Response(
                content=cached.body,
                status_code=cached.status_code,
                headers={**cached.headers, "X-Idempotent-Replay": "true"},
            )

        # 并发去重
        if self.store.is_in_progress(key):
            return JSONResponse(
                status_code=409,
                content={
                    "error": "duplicate_in_progress",
                    "detail": "Same request is being processed",
                },
            )

        self.store.mark_progress(key)
        try:
            response = await call_next(request)

            # 缓存成功响应
            if response.status_code < 500:
                body = b""
                async for chunk in cast(Any, response).body_iterator:
                    body += chunk if isinstance(chunk, bytes) else chunk.encode()

                self.store.set(key, CachedResponse(
                    status_code=response.status_code,
                    body=body,
                    headers=dict(response.headers),
                ))

                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

            return response
        finally:
            self.store.complete_progress(key)
