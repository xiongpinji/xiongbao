"""API 响应缓存中间件：ETag + 条件请求（304）。

对 GET 请求自动生成 ETag，客户端携带 If-None-Match 时返回 304 节省带宽。
可选内存缓存层减少重复计算。

用法：
    from xagent.api.response_cache import ResponseCacheMiddleware
    app.add_middleware(ResponseCacheMiddleware, cache_ttl=60)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.cache")


@dataclass
class CacheEntry:
    """缓存条目。"""

    body: bytes
    etag: str
    content_type: str
    status_code: int
    created_at: float = field(default_factory=time.time)


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    """ETag 条件请求 + 可选内存缓存。"""

    def __init__(self, app, cache_ttl: int = 60, max_entries: int = 500):
        super().__init__(app)
        self.cache_ttl = cache_ttl
        self.max_entries = max_entries
        self._cache: dict[str, CacheEntry] = {}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 仅缓存 GET 请求
        if request.method != "GET":
            return await call_next(request)

        # 跳过流式端点
        path = request.url.path
        if "/stream" in path or "/ws" in path:
            return await call_next(request)

        cache_key = f"{path}?{request.url.query}"

        # 检查内存缓存
        entry = self._cache.get(cache_key)
        if entry and (time.time() - entry.created_at) < self.cache_ttl:
            # 条件请求：If-None-Match
            if_none_match = request.headers.get("if-none-match")
            if if_none_match and if_none_match == entry.etag:
                return Response(status_code=304, headers={"ETag": entry.etag})

            return Response(
                content=entry.body,
                status_code=entry.status_code,
                media_type=entry.content_type,
                headers={
                    "ETag": entry.etag,
                    "Cache-Control": f"private, max-age={self.cache_ttl}",
                    "X-Cache": "HIT",
                },
            )

        # 执行实际请求
        response = await call_next(request)

        # 仅缓存成功响应
        if response.status_code != 200:
            return response

        # 读取 body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, bytes) else chunk.encode()

        # 计算 ETag
        etag = f'"{hashlib.md5(body).hexdigest()[:16]}"'

        # 条件请求检查
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and if_none_match == etag:
            return Response(status_code=304, headers={"ETag": etag})

        # 存入缓存
        if len(self._cache) >= self.max_entries:
            # LRU 简化：清除最旧 25%
            sorted_keys = sorted(self._cache, key=lambda k: self._cache[k].created_at)
            for k in sorted_keys[: self.max_entries // 4]:
                del self._cache[k]

        self._cache[cache_key] = CacheEntry(
            body=body,
            etag=etag,
            content_type=response.media_type or "application/json",
            status_code=response.status_code,
        )

        return Response(
            content=body,
            status_code=response.status_code,
            media_type=response.media_type,
            headers={
                "ETag": etag,
                "Cache-Control": f"private, max-age={self.cache_ttl}",
                "X-Cache": "MISS",
            },
        )
