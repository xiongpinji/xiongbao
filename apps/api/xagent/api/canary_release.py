"""灰度发布：流量百分比路由。

功能：
- 按百分比将流量路由到新版本
- 按用户/租户白名单强制路由
- 渐进式放量（1% → 10% → 50% → 100%）
- 版本标记响应头

用法：
    from xagent.api.canary_release import canary_router

    canary_router.set_weight("v2", percent=10)
    canary_router.whitelist("v2", tenants=["tenant_vip"])
    # 中间件：
    app.add_middleware(CanaryMiddleware, router=canary_router)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.canary")

HEADER_VERSION = "X-Served-Version"


@dataclass
class CanaryConfig:
    """灰度配置。"""

    version: str
    percent: float = 0.0  # 流量百分比 0-100
    whitelist_tenants: set[str] = field(default_factory=set)
    whitelist_users: set[str] = field(default_factory=set)
    enabled: bool = True
    started_at: float = field(default_factory=time.time)


class CanaryRouter:
    """灰度路由器。"""

    def __init__(self, stable_version: str = "v1"):
        self.stable_version = stable_version
        self._configs: dict[str, CanaryConfig] = {}

    def set_weight(self, version: str, percent: float) -> None:
        """设置版本流量百分比。"""
        percent = max(0, min(100, percent))
        if version not in self._configs:
            self._configs[version] = CanaryConfig(version=version)
        self._configs[version].percent = percent
        logger.info("canary weight: %s → %.1f%%", version, percent)

    def whitelist(self, version: str, tenants: list[str] | None = None, users: list[str] | None = None) -> None:
        """白名单强制路由。"""
        if version not in self._configs:
            self._configs[version] = CanaryConfig(version=version)
        cfg = self._configs[version]
        if tenants:
            cfg.whitelist_tenants.update(tenants)
        if users:
            cfg.whitelist_users.update(users)

    def resolve(self, tenant: str = "", user: str = "", request_id: str = "") -> str:
        """决定路由版本。"""
        # 白名单优先
        for version, cfg in self._configs.items():
            if not cfg.enabled:
                continue
            if tenant in cfg.whitelist_tenants or user in cfg.whitelist_users:
                return version

        # 百分比路由（基于 request_id 哈希，保证同一请求一致）
        for version, cfg in self._configs.items():
            if not cfg.enabled or cfg.percent <= 0:
                continue
            if cfg.percent >= 100:
                return version
            # 一致性哈希
            hash_val = int(hashlib.md5(request_id.encode()).hexdigest()[:8], 16)
            if (hash_val % 10000) < cfg.percent * 100:
                return version

        return self.stable_version

    def promote(self, version: str) -> None:
        """全量发布。"""
        self.set_weight(version, 100)
        logger.info("canary promoted: %s → 100%%", version)

    def rollback(self, version: str) -> None:
        """回滚（流量归零）。"""
        self.set_weight(version, 0)
        if version in self._configs:
            self._configs[version].enabled = False
        logger.info("canary rolled back: %s", version)

    @property
    def status(self) -> dict:
        return {
            "stable": self.stable_version,
            "canaries": {
                v: {"percent": c.percent, "enabled": c.enabled, "whitelist_tenants": len(c.whitelist_tenants)}
                for v, c in self._configs.items()
            },
        }


class CanaryMiddleware(BaseHTTPMiddleware):
    """灰度路由中间件（标记版本头）。"""

    def __init__(self, app, router: CanaryRouter | None = None):
        super().__init__(app)
        self.router = router or canary_router

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        tenant = request.headers.get("x-tenant-id", "")
        user = request.headers.get("x-user-id", "")
        request_id = request.headers.get("x-request-id", str(time.time()))

        version = self.router.resolve(tenant=tenant, user=user, request_id=request_id)

        # 注入到 request state
        request.state.api_version = version

        response = await call_next(request)
        response.headers[HEADER_VERSION] = version
        return response


# 全局单例
canary_router = CanaryRouter(stable_version="v1")
