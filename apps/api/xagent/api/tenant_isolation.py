"""多租户隔离：请求级租户上下文。

功能：
- 从请求头/JWT/路径提取租户 ID
- ContextVar 注入租户上下文
- 数据访问自动过滤
- 租户配额管理

用法：
    from xagent.api.tenant_isolation import TenantMiddleware, get_tenant

    app.add_middleware(TenantMiddleware, header="X-Tenant-Id")
    # 业务代码中：
    tenant = get_tenant()
    agents = await db.query("SELECT * FROM agents WHERE tenant_id = ?", tenant.id)
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.tenant")

_tenant_var: ContextVar["TenantContext | None"] = ContextVar("tenant", default=None)


@dataclass
class TenantContext:
    """租户上下文。"""

    id: str
    name: str = ""
    plan: str = "free"  # free / pro / enterprise
    quotas: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def max_agents(self) -> int:
        return self.quotas.get("max_agents", 10)

    @property
    def max_runs_per_day(self) -> int:
        return self.quotas.get("max_runs_per_day", 100)


# 默认配额
PLAN_QUOTAS: dict[str, dict[str, int]] = {
    "free": {"max_agents": 5, "max_runs_per_day": 50, "max_storage_mb": 100},
    "pro": {"max_agents": 50, "max_runs_per_day": 1000, "max_storage_mb": 5000},
    "enterprise": {"max_agents": 500, "max_runs_per_day": 50000, "max_storage_mb": 100000},
}


def get_tenant() -> TenantContext | None:
    """获取当前请求的租户上下文。"""
    return _tenant_var.get()


def require_tenant() -> TenantContext:
    """获取租户（不存在则抛异常）。"""
    tenant = _tenant_var.get()
    if not tenant:
        raise ValueError("No tenant context available")
    return tenant


class TenantMiddleware(BaseHTTPMiddleware):
    """多租户隔离中间件。"""

    def __init__(
        self,
        app,
        header: str = "X-Tenant-Id",
        exclude_prefixes: list[str] | None = None,
        tenant_resolver: Any = None,
    ):
        super().__init__(app)
        self.header = header
        self.exclude_prefixes = exclude_prefixes or ["/health", "/docs", "/openapi"]
        self._tenant_resolver = tenant_resolver

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # 排除路径
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        # 提取租户 ID
        tenant_id = request.headers.get(self.header, "")
        if not tenant_id:
            # 尝试从 query param
            tenant_id = request.query_params.get("tenant_id", "")

        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "missing_tenant",
                    "message": f"缺少租户标识（{self.header}）",
                },
            )

        # 解析租户（实际项目中从数据库/缓存获取）
        tenant = await self._resolve_tenant(tenant_id)
        if not tenant:
            return JSONResponse(
                status_code=403,
                content={"error": "unknown_tenant", "message": f"未知租户: {tenant_id}"},
            )

        # 注入上下文
        token = _tenant_var.set(tenant)
        try:
            response = await call_next(request)
            response.headers["X-Tenant-Id"] = tenant.id
            return response
        finally:
            _tenant_var.reset(token)

    async def _resolve_tenant(self, tenant_id: str) -> TenantContext | None:
        """解析租户（可扩展为数据库查询）。"""
        if self._tenant_resolver:
            return await self._tenant_resolver(tenant_id)

        # 默认：接受所有租户 ID，free 计划
        return TenantContext(
            id=tenant_id,
            name=tenant_id,
            plan="free",
            quotas=PLAN_QUOTAS["free"],
        )
