"""API 版本协商：Content Negotiation + 版本路由。

支持多种版本指定方式（优先级从高到低）：
1. URL 路径：/api/v1/agents
2. 请求头：Accept: application/vnd.xagent.v1+json
3. 查询参数：?version=v1
4. 自定义头：X-API-Version: v1

用法：
    from xagent.api.version_negotiation import negotiate_version, VersionedRouter
    version = negotiate_version(request)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import Request

from xagent.infra.logging import get_logger

logger = get_logger("xagent.version")

# 支持的版本
SUPPORTED_VERSIONS = ["v1"]
DEFAULT_VERSION = "v1"
LATEST_VERSION = "v1"

# Accept 头正则：application/vnd.xagent.v1+json
ACCEPT_RE = re.compile(r"application/vnd\.xagent\.(v\d+)\+json")


@dataclass
class VersionInfo:
    """版本协商结果。"""

    version: str
    source: str  # "path" | "accept" | "query" | "header" | "default"
    deprecated: bool = False


def negotiate_version(request: Request) -> VersionInfo:
    """从请求中协商 API 版本。"""

    # 1. URL 路径（/api/v1/...）
    path = request.url.path
    path_match = re.match(r"/api/(v\d+)/", path)
    if path_match:
        version = path_match.group(1)
        if version in SUPPORTED_VERSIONS:
            return VersionInfo(version=version, source="path")

    # 2. Accept 头
    accept = request.headers.get("accept", "")
    accept_match = ACCEPT_RE.search(accept)
    if accept_match:
        version = accept_match.group(1)
        if version in SUPPORTED_VERSIONS:
            return VersionInfo(version=version, source="accept")

    # 3. 查询参数
    query_version = request.query_params.get("version", "")
    if query_version and query_version in SUPPORTED_VERSIONS:
        return VersionInfo(version=query_version, source="query")

    # 4. 自定义头
    header_version = request.headers.get("x-api-version", "")
    if header_version and header_version in SUPPORTED_VERSIONS:
        return VersionInfo(version=header_version, source="header")

    # 默认
    return VersionInfo(version=DEFAULT_VERSION, source="default")


def get_version_headers(version: str) -> dict[str, str]:
    """生成版本相关响应头。"""
    headers = {
        "X-API-Version": version,
        "X-API-Latest": LATEST_VERSION,
    }
    # 废弃警告
    if version not in SUPPORTED_VERSIONS:
        headers["Warning"] = f'299 - "API version {version} is deprecated"'
    return headers


class APIVersionMiddleware:
    """版本协商中间件（注入版本到 request.state）。"""

    async def __call__(self, request: Request, call_next):
        version_info = negotiate_version(request)
        request.state.api_version = version_info.version
        request.state.version_source = version_info.source

        response = await call_next(request)

        # 注入版本响应头
        for key, value in get_version_headers(version_info.version).items():
            response.headers[key] = value

        return response
