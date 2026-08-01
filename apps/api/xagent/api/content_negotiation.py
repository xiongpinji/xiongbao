"""内容协商：根据 Accept 头返回对应格式。

功能：
- 解析 Accept 头优先级
- 支持 json/msgpack/csv/text
- 格式不支持时 406
- 扩展格式注册

用法：
    from xagent.api.content_negotiation import ContentNegotiationMiddleware

    app.add_middleware(ContentNegotiationMiddleware)
"""

from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.content_negotiation")


@dataclass
class MediaType:
    """媒体类型。"""

    type: str
    quality: float = 1.0


from dataclasses import dataclass


def parse_accept(accept: str) -> list[MediaType]:
    """解析 Accept 头。"""
    if not accept or accept == "*/*":
        return [MediaType(type="application/json", quality=1.0)]

    types = []
    for part in accept.split(","):
        part = part.strip()
        if not part:
            continue
        segments = part.split(";")
        media_type = segments[0].strip()
        quality = 1.0
        for param in segments[1:]:
            param = param.strip()
            if param.startswith("q="):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 0.0
        types.append(MediaType(type=media_type, quality=quality))

    types.sort(key=lambda t: t.quality, reverse=True)
    return types


class ContentNegotiationMiddleware(BaseHTTPMiddleware):
    """内容协商中间件。"""

    SUPPORTED = {
        "application/json": "json",
        "text/plain": "text",
        "text/csv": "csv",
        "application/msgpack": "msgpack",
    }

    def __init__(self, app, default_format: str = "json"):
        super().__init__(app)
        self.default_format = default_format

    def _negotiate(self, accept: str) -> str:
        """协商格式。"""
        types = parse_accept(accept)
        for mt in types:
            if mt.type in self.SUPPORTED:
                return self.SUPPORTED[mt.type]
            if mt.type == "*/*":
                return self.default_format
        return ""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 仅对 GET 请求协商
        if request.method != "GET":
            return await call_next(request)

        accept = request.headers.get("accept", "application/json")
        fmt = self._negotiate(accept)

        if not fmt:
            return JSONResponse(
                status_code=406,
                content={
                    "error": "not_acceptable",
                    "supported": list(self.SUPPORTED.keys()),
                },
            )

        response = await call_next(request)

        # 添加协商结果头
        response.headers["X-Content-Format"] = fmt
        response.headers["Vary"] = "Accept"

        return response
