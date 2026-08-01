"""响应压缩：按 Accept-Encoding 压缩响应体。

功能：
- gzip/deflate 压缩
- 最小压缩阈值
- 排除已压缩类型
- 压缩统计

用法：
    from xagent.api.response_compression import CompressionMiddleware

    app.add_middleware(CompressionMiddleware, minimum_size=500)
"""

from __future__ import annotations

import gzip
import zlib
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.compression")

# 不压缩的 Content-Type
SKIP_TYPES = {"image/", "video/", "audio/", "application/zip", "application/gzip"}


class CompressionMiddleware(BaseHTTPMiddleware):
    """响应压缩中间件。"""

    def __init__(
        self,
        app,
        minimum_size: int = 500,
        gzip_level: int = 6,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.minimum_size = minimum_size
        self.gzip_level = gzip_level
        self.exclude_prefixes = exclude_prefixes or ["/ws"]

        # 统计
        self._total_compressed = 0
        self._total_skipped = 0
        self._bytes_saved = 0

    def _should_compress(self, request: Request, response: Response) -> str | None:
        """判断是否应压缩，返回编码方式。"""
        # 已编码
        if "content-encoding" in response.headers:
            return None

        # 大小阈值
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) < self.minimum_size:
            return None

        # Content-Type 排除
        content_type = response.headers.get("content-type", "")
        for skip in SKIP_TYPES:
            if content_type.startswith(skip):
                return None

        # Accept-Encoding
        accept = request.headers.get("accept-encoding", "")
        if "gzip" in accept:
            return "gzip"
        if "deflate" in accept:
            return "deflate"
        return None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        response = await call_next(request)

        encoding = self._should_compress(request, response)
        if not encoding:
            self._total_skipped += 1
            return response

        # 读取 body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, bytes) else chunk.encode()

        if len(body) < self.minimum_size:
            self._total_skipped += 1
            return Response(content=body, status_code=response.status_code, headers=dict(response.headers))

        # 压缩
        original_size = len(body)
        if encoding == "gzip":
            compressed = gzip.compress(body, compresslevel=self.gzip_level)
        else:
            compressed = zlib.compress(body, level=self.gzip_level)

        self._total_compressed += 1
        self._bytes_saved += original_size - len(compressed)

        headers = dict(response.headers)
        headers["content-encoding"] = encoding
        headers["content-length"] = str(len(compressed))
        headers["vary"] = "Accept-Encoding"

        return Response(
            content=compressed,
            status_code=response.status_code,
            headers=headers,
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_compressed": self._total_compressed,
            "total_skipped": self._total_skipped,
            "bytes_saved": self._bytes_saved,
        }
