"""API 版本路由：多版本共存。

功能：
- URL 路径版本（/api/v1/, /api/v2/）
- Header 版本（Accept: application/vnd.xagent.v2+json）
- 版本废弃标记 + Sunset 头
- 默认版本回退

用法：
    from xagent.api.version_router import VersionRouter

    router = VersionRouter(default_version="v1", latest_version="v2")
    router.register("v1", legacy_routes)
    router.register("v2", new_routes, deprecated_after="2027-01-01")
    app.mount("/api", router.asgi_app)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Router
from starlette.types import ASGIApp, Receive, Scope, Send

from xagent.infra.logging import get_logger

logger = get_logger("xagent.versioning")

# 版本路径正则
VERSION_PATH_RE = re.compile(r"^/v(\d+)/")

# 自定义 Accept 版本正则
ACCEPT_VERSION_RE = re.compile(
    r"application/vnd\.xagent\.v(\d+)\+json"
)


@dataclass
class VersionInfo:
    """版本注册信息。"""

    version: str
    routes: Any = None
    deprecated: bool = False
    deprecated_after: str | None = None  # ISO date
    sunset_date: str | None = None
    description: str = ""


class VersionRouter:
    """API 版本路由器。"""

    def __init__(
        self,
        default_version: str = "v1",
        latest_version: str = "v1",
    ):
        self.default_version = default_version
        self.latest_version = latest_version
        self._versions: dict[str, VersionInfo] = {}

    def register(
        self,
        version: str,
        routes: Any = None,
        deprecated: bool = False,
        deprecated_after: str | None = None,
        sunset_date: str | None = None,
        description: str = "",
    ) -> None:
        """注册版本。"""
        self._versions[version] = VersionInfo(
            version=version,
            routes=routes,
            deprecated=deprecated,
            deprecated_after=deprecated_after,
            sunset_date=sunset_date,
            description=description,
        )
        logger.info("API version registered: %s", version)

    def resolve_version(self, request: Request) -> str:
        """从请求中解析版本。"""
        # 1. URL 路径
        path = request.url.path
        match = VERSION_PATH_RE.match(path)
        if match:
            version = f"v{match.group(1)}"
            if version in self._versions:
                return version

        # 2. Accept 头
        accept = request.headers.get("accept", "")
        accept_match = ACCEPT_VERSION_RE.search(accept)
        if accept_match:
            version = f"v{accept_match.group(1)}"
            if version in self._versions:
                return version

        # 3. X-API-Version 头
        header_version = request.headers.get("x-api-version", "")
        if header_version in self._versions:
            return header_version

        # 4. 默认版本
        return self.default_version

    def get_version_info(self, version: str) -> VersionInfo | None:
        return self._versions.get(version)

    def version_headers(self, version: str) -> dict[str, str]:
        """生成版本相关响应头。"""
        headers: dict[str, str] = {
            "X-API-Version": version,
            "X-API-Latest": self.latest_version,
        }

        info = self._versions.get(version)
        if info and info.deprecated:
            headers["Deprecation"] = "true"
            if info.sunset_date:
                headers["Sunset"] = info.sunset_date
            if info.deprecated_after:
                headers["X-Deprecated-After"] = info.deprecated_after

        return headers

    def list_versions(self) -> list[dict[str, Any]]:
        """列出所有版本信息。"""
        return [
            {
                "version": v.version,
                "deprecated": v.deprecated,
                "sunset_date": v.sunset_date,
                "description": v.description,
                "is_default": v.version == self.default_version,
                "is_latest": v.version == self.latest_version,
            }
            for v in self._versions.values()
        ]


# 全局单例
version_router = VersionRouter(default_version="v1", latest_version="v2")
