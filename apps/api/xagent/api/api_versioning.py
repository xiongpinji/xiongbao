"""API 版本管理：多版本路由与弃用策略。

功能：
- URL/Header 版本解析
- 版本弃用警告
- 日落日期
- 版本协商

用法：
    from xagent.api.api_versioning import VersionMiddleware

    app.add_middleware(
        VersionMiddleware,
        current_version="v2",
        deprecated_versions={"v1": "2026-12-31"},
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.versioning")


@dataclass
class VersionInfo:
    """版本信息。"""

    version: str
    deprecated: bool = False
    sunset_date: str = ""
    is_current: bool = False


class VersionMiddleware(BaseHTTPMiddleware):
    """API 版本中间件。"""

    def __init__(
        self,
        app,
        current_version: str = "v1",
        supported_versions: list[str] | None = None,
        deprecated_versions: dict[str, str] | None = None,
        version_header: str = "x-api-version",
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.current_version = current_version
        self.supported_versions = supported_versions or [current_version]
        self.deprecated_versions = deprecated_versions or {}
        self.version_header = version_header
        self.exclude_prefixes = exclude_prefixes or ["/health", "/ws"]

    def _resolve_version(self, request: Request) -> str:
        """解析请求版本。"""
        # 1. Header 优先
        header_version = request.headers.get(self.version_header)
        if header_version:
            return header_version

        # 2. URL 路径 (/v1/xxx)
        path = request.url.path
        parts = path.strip("/").split("/")
        if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
            return parts[0]

        # 3. 查询参数
        query_version = request.query_params.get("version")
        if query_version:
            return query_version

        # 默认当前版本
        return self.current_version

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        version = self._resolve_version(request)

        # 不支持的版本
        if version not in self.supported_versions:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "unsupported_version",
                    "detail": f"Version '{version}' is not supported",
                    "supported": self.supported_versions,
                    "current": self.current_version,
                },
            )

        response = await call_next(request)

        # 添加版本头
        response.headers["X-API-Version"] = version
        response.headers["X-API-Current"] = self.current_version

        # 弃用警告
        if version in self.deprecated_versions:
            sunset = self.deprecated_versions[version]
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = sunset
            response.headers["Warning"] = f'299 - "API {version} is deprecated, sunset: {sunset}"'
            logger.warning("deprecated version used: %s path=%s", version, path)

        return response

    def get_versions(self) -> list[dict[str, Any]]:
        """获取所有版本信息。"""
        return [
            {
                "version": v,
                "is_current": v == self.current_version,
                "deprecated": v in self.deprecated_versions,
                "sunset": self.deprecated_versions.get(v, ""),
            }
            for v in self.supported_versions
        ]
