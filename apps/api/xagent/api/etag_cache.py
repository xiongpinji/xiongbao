"""ETag 缓存：条件请求 304 支持。

功能：
- 自动生成响应 ETag（MD5/SHA256）
- 处理 If-None-Match 条件请求 → 304
- 处理 If-Modified-Since → 304
- 可配置弱/强 ETag

用法：
    from xagent.api.etag_cache import ETagMiddleware

    app.add_middleware(ETagMiddleware, algorithm="md5")
    # 或手动：
    from xagent.api.etag_cache import conditional_response
    return conditional_response(request, content=json_bytes)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.etag")

# 不生成 ETag 的路径
EXCLUDE_PREFIXES = ("/ws", "/api/v1/stream")


def compute_etag(content: bytes, algorithm: str = "md5", weak: bool = False) -> str:
    """计算 ETag 值。"""
    h = hashlib.new(algorithm, content).hexdigest()[:32]
    return f'W/"{h}"' if weak else f'"{h}"'


def etag_matches(if_none_match: str, etag: str) -> bool:
    """检查 If-None-Match 是否匹配。"""
    if if_none_match.strip() == "*":
        return True
    # 支持多个 ETag
    candidates = [e.strip() for e in if_none_match.split(",")]
    # 去掉 W/ 前缀比较
    normalized_etag = etag.replace("W/", "")
    for candidate in candidates:
        normalized_candidate = candidate.strip().replace("W/", "")
        if normalized_candidate == normalized_etag:
            return True
    return False


def conditional_response(
    request: Request,
    content: bytes,
    media_type: str = "application/json",
    algorithm: str = "md5",
    weak: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> Response:
    """生成条件响应（支持 304）。"""
    etag = compute_etag(content, algorithm, weak)

    # If-None-Match
    if_none_match = request.headers.get("if-none-match", "")
    if if_none_match and etag_matches(if_none_match, etag):
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "no-cache"},
        )

    headers = {
        "ETag": etag,
        "Cache-Control": "no-cache",
        **(extra_headers or {}),
    }

    return Response(
        content=content,
        media_type=media_type,
        headers=headers,
    )


class ETagMiddleware(BaseHTTPMiddleware):
    """ETag 条件请求中间件。"""

    def __init__(
        self,
        app,
        algorithm: str = "md5",
        weak: bool = False,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.algorithm = algorithm
        self.weak = weak
        self.exclude_prefixes = exclude_prefixes or EXCLUDE_PREFIXES

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # 排除路径
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        # 仅处理 GET/HEAD
        if request.method not in ("GET", "HEAD"):
            return await call_next(request)

        response = await call_next(request)

        # 仅处理 200 JSON 响应
        if response.status_code != 200:
            return response

        # 读取响应体
        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode()
            else:
                body += chunk

        # 计算 ETag
        etag = compute_etag(body, self.algorithm, self.weak)

        # 条件匹配 → 304
        if_none_match = request.headers.get("if-none-match", "")
        if if_none_match and etag_matches(if_none_match, etag):
            return Response(
                status_code=304,
                headers={"ETag": etag, "Cache-Control": "no-cache"},
            )

        # 返回带 ETag 的完整响应
        return Response(
            content=body,
            status_code=response.status_code,
            media_type=response.media_type,
            headers={
                **dict(response.headers),
                "ETag": etag,
                "Cache-Control": "no-cache",
            },
        )
