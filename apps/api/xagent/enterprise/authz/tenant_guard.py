"""多租户数据隔离守卫。

提供：
- ``TenantScope`` 依赖：从 Principal 提取 tenant_id，确保所有数据操作限定在租户范围内。
- ``scoped_filter()`` 工具：为查询条件注入 tenant_id 过滤。
- ``assert_same_tenant()`` 工具：跨租户访问检测。

用法：
    @router.get("/items")
    async def list_items(scope: TenantScope = Depends(get_tenant_scope)):
        items = store.list(tenant_id=scope.tenant_id)
        ...
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status

from xagent.enterprise.auth.dependencies import get_principal
from xagent.enterprise.auth.principal import Principal


@dataclass(frozen=True)
class TenantScope:
    """租户作用域，贯穿请求生命周期。"""

    tenant_id: str
    user_id: str
    is_admin: bool

    def assert_access(self, resource_tenant_id: str) -> None:
        """校验目标资源属于当前租户，否则拒绝。"""
        if not self.is_admin and resource_tenant_id != self.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="跨租户访问被拒绝",
            )


def get_tenant_scope(principal: Principal = Depends(get_principal)) -> TenantScope:
    """FastAPI 依赖：从认证主体构造租户作用域。"""
    return TenantScope(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        is_admin=principal.has_role("admin"),
    )


def scoped_filter(tenant_id: str, items: list, attr: str = "tenant_id") -> list:
    """内存列表按 tenant_id 过滤（用于非 DB 场景）。"""
    return [item for item in items if getattr(item, attr, None) == tenant_id]


def assert_same_tenant(principal_tenant: str, resource_tenant: str) -> None:
    """断言两个 tenant_id 一致，否则抛 403。"""
    if principal_tenant != resource_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="跨租户访问被拒绝",
        )
