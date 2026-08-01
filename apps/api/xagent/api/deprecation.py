"""API 废弃中间件：Deprecation/Sunset 头注入。

功能：
- 按路径标记废弃端点
- 注入 Deprecation + Sunset 响应头
- 废弃警告日志
- 统计废弃端点调用量

用法：
    from xagent.api.deprecation import DeprecationMiddleware

    app.add_middleware(DeprecationMiddleware, deprecated_paths={
        "/api/v1/agents/legacy": "2027-06-01",
        "/api/v1/old-export": "2027-03-01",
    })
"""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.deprecation")


class DeprecationMiddleware(BaseHTTPMiddleware):
    """API 废弃标记中间件。"""

    def __init__(
        self,
        app,
        deprecated_paths: dict[str, str] | None = None,
        deprecated_prefixes: dict[str, str] | None = None,
        link_url: str = "",
    ):
        """
        Args:
            deprecated_paths: 精确路径 → sunset 日期映射
            deprecated_prefixes: 路径前缀 → sunset 日期映射
            link_url: 迁移文档链接
        """
        super().__init__(app)
        self.deprecated_paths = deprecated_paths or {}
        self.deprecated_prefixes = deprecated_prefixes or {}
        self.link_url = link_url
        self._call_counts: dict[str, int] = defaultdict(int)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        sunset_date = self._get_sunset(path)

        response = await call_next(request)

        if sunset_date:
            self._call_counts[path] += 1

            # 注入废弃头
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = sunset_date
            if self.link_url:
                response.headers["Link"] = f'<{self.link_url}>; rel="deprecation"; type="text/html"'

            # 定期告警（每100次）
            count = self._call_counts[path]
            if count == 1 or count % 100 == 0:
                logger.warning(
                    "deprecated endpoint called: %s (count=%d, sunset=%s)",
                    path,
                    count,
                    sunset_date,
                )

        return response

    def _get_sunset(self, path: str) -> str | None:
        """查找路径对应的 sunset 日期。"""
        # 精确匹配
        if path in self.deprecated_paths:
            return self.deprecated_paths[path]
        # 前缀匹配
        for prefix, date in self.deprecated_prefixes.items():
            if path.startswith(prefix):
                return date
        return None

    @property
    def stats(self) -> dict[str, int]:
        """废弃端点调用统计。"""
        return dict(self._call_counts)


# 预配置示例
DEFAULT_DEPRECATED = {
    "/api/v1/agents/legacy-run": "2027-06-01",
    "/api/v1/export/csv-old": "2027-03-01",
}
