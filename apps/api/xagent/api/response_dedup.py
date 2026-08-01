"""响应去重哈希：相同响应体只传输一次。

功能：
- 响应体 SHA256 哈希
- 相同哈希返回 304（配合客户端缓存）
- 大响应分块哈希
- 中间件模式

用法：
    from xagent.api.response_dedup import ResponseDedupMiddleware

    app.add_middleware(ResponseDedupMiddleware)
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.resp_dedup")

HEADER_CONTENT_HASH = "X-Content-Hash"


class HashCache:
    """哈希 LRU 缓存。"""

    def __init__(self, max_size: int = 5000, ttl_s: float = 300):
        self.max_size = max_size
        self.ttl_s = ttl_s
        self._cache: OrderedDict[str, float] = OrderedDict()

    def get(self, key: str) -> bool:
        if key in self._cache:
            ts = self._cache[key]
            if time.time() - ts < self.ttl_s:
                self._cache.move_to_end(key)
                return True
            del self._cache[key]
        return False

    def set(self, key: str) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = time.time()
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)


class ResponseDedupMiddleware(BaseHTTPMiddleware):
    """响应去重中间件。"""

    def __init__(
        self,
        app,
        cache_size: int = 5000,
        ttl_s: float = 300,
        min_body_size: int = 1024,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.cache = HashCache(max_size=cache_size, ttl_s=ttl_s)
        self.min_body_size = min_body_size
        self.exclude_prefixes = exclude_prefixes or ["/ws", "/api/v1/stream"]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # 排除路径
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        # 仅 GET 请求
        if request.method != "GET":
            return await call_next(request)

        response = await call_next(request)

        # 仅处理 JSON 响应
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # 读取响应体
        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode()
            else:
                body += chunk

        # 小响应跳过
        if len(body) < self.min_body_size:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # 计算哈希
        content_hash = hashlib.sha256(body).hexdigest()[:16]

        # 检查客户端是否已有此内容
        client_hash = request.headers.get("X-If-Content-Hash")
        if client_hash and client_hash == content_hash:
            return Response(status_code=304, headers={HEADER_CONTENT_HASH: content_hash})

        # 缓存哈希
        self.cache.set(content_hash)

        # 返回带哈希头的响应
        headers = dict(response.headers)
        headers[HEADER_CONTENT_HASH] = content_hash

        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
