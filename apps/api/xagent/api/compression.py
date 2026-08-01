"""API 响应压缩：Gzip / Brotli 中间件。

功能：
- 自动压缩响应体（> 最小阈值）
- 根据 Accept-Encoding 选择算法（br > gzip）
- 跳过已压缩 / 流式响应
- 可配置最小压缩阈值

用法：
    from xagent.api.compression import CompressionMiddleware
    app.add_middleware(CompressionMiddleware, minimum_size=500)
"""

from __future__ import annotations

import gzip
import io
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from xagent.infra.logging import get_logger

logger = get_logger("xagent.compression")

# 不应压缩的 Content-Type
SKIP_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "video/mp4",
    "audio/mpeg",
    "application/zip",
    "application/gzip",
}


class CompressionMiddleware(BaseHTTPMiddleware):
    """响应压缩中间件。

    优先级：br（Brotli，如可用）> gzip。
    仅压缩超过 minimum_size 的响应。
    """

    def __init__(self, app, minimum_size: int = 500, compress_level: int = 6):
        super().__init__(app)
        self.minimum_size = minimum_size
        self.compress_level = compress_level
        # 检测 brotli 是否可用
        self._has_brotli = False
        try:
            import brotli  # noqa: F401

            self._has_brotli = True
        except ImportError:
            pass

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        # 跳过流式响应
        if isinstance(response, StreamingResponse):
            return response

        # 跳过已编码
        if "Content-Encoding" in response.headers:
            return response

        # 检查 Accept-Encoding
        accept_encoding = request.headers.get("accept-encoding", "")
        if not accept_encoding:
            return response

        # 获取响应体
        body = response.body
        if len(body) < self.minimum_size:
            return response

        # 检查 Content-Type 是否应跳过
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if content_type in SKIP_CONTENT_TYPES:
            return response

        # 选择压缩算法
        encoding = self._select_encoding(accept_encoding)
        if not encoding:
            return response

        # 压缩
        compressed = self._compress(body, encoding)
        if compressed is None or len(compressed) >= len(body):
            return response  # 压缩后更大，不压缩

        # 构建新响应
        headers = dict(response.headers)
        headers["Content-Encoding"] = encoding
        headers["Content-Length"] = str(len(compressed))
        headers["Vary"] = "Accept-Encoding"

        # 压缩比日志（调试用）
        ratio = len(compressed) / len(body) * 100
        logger.debug(
            "compressed %s: %d → %d bytes (%.1f%%)",
            encoding,
            len(body),
            len(compressed),
            ratio,
        )

        return Response(
            content=compressed,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )

    def _select_encoding(self, accept_encoding: str) -> str | None:
        """根据 Accept-Encoding 选择最优算法。"""
        if self._has_brotli and "br" in accept_encoding:
            return "br"
        if "gzip" in accept_encoding:
            return "gzip"
        return None

    def _compress(self, data: bytes, encoding: str) -> bytes | None:
        """执行压缩。"""
        try:
            if encoding == "gzip":
                buf = io.BytesIO()
                with gzip.GzipFile(
                    fileobj=buf, mode="wb", compresslevel=self.compress_level
                ) as f:
                    f.write(data)
                return buf.getvalue()
            elif encoding == "br":
                import brotli

                return brotli.compress(data, quality=self.compress_level)
        except Exception as exc:
            logger.warning("compression failed (%s): %s", encoding, exc)
        return None
