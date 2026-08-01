"""请求体大小限制：防止超大请求 DoS。

功能：
- 限制请求体大小（默认 10MB）
- 按路径配置不同限制
- 返回 413 Payload Too Large
- 支持 Content-Length 预检

用法：
    from xagent.api.body_limit import BodyLimitMiddleware
    app.add_middleware(BodyLimitMiddleware, max_size=10 * 1024 * 1024)
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.body_limit")

# 路径特定限制（bytes）
PATH_LIMITS: dict[str, int] = {
    "/api/v1/upload": 50 * 1024 * 1024,  # 上传 50MB
    "/api/v1/import": 20 * 1024 * 1024,  # 导入 20MB
}

# 不检查的方法
SKIP_METHODS = {"GET", "HEAD", "OPTIONS"}


class BodyLimitMiddleware(BaseHTTPMiddleware):
    """请求体大小限制中间件。"""

    def __init__(
        self,
        app,
        max_size: int = 10 * 1024 * 1024,  # 10MB
        path_limits: dict[str, int] | None = None,
    ):
        super().__init__(app)
        self.max_size = max_size
        self.path_limits = path_limits or PATH_LIMITS

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 跳过无 body 的方法
        if request.method in SKIP_METHODS:
            return await call_next(request)

        # 确定限制
        limit = self._get_limit(request.url.path)

        # Content-Length 预检
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > limit:
                    return self._too_large(size, limit, request.url.path)
            except ValueError:
                pass

        # 读取并检查实际 body 大小
        body = await request.body()
        if len(body) > limit:
            return self._too_large(len(body), limit, request.url.path)

        return await call_next(request)

    def _get_limit(self, path: str) -> int:
        """获取路径对应的限制。"""
        for prefix, limit in self.path_limits.items():
            if path.startswith(prefix):
                return limit
        return self.max_size

    def _too_large(self, size: int, limit: int, path: str) -> JSONResponse:
        """返回 413 响应。"""
        size_mb = size / 1024 / 1024
        limit_mb = limit / 1024 / 1024
        logger.warning(
            "body too large: %.1fMB > %.1fMB (%s)", size_mb, limit_mb, path
        )
        return JSONResponse(
            status_code=413,
            content={
                "error": "payload_too_large",
                "message": f"请求体过大（{size_mb:.1f}MB），限制 {limit_mb:.0f}MB",
                "max_size": limit,
                "actual_size": size,
            },
        )
