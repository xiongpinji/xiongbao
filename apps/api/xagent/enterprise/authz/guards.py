"""授权守卫：FastAPI 依赖，组合「认证 + 资源/动作授权」。

用法：
    @router.post("/agents/run", dependencies=[Depends(require_permission("agent", "execute"))])
或注入拿 principal：
    principal: Principal = Depends(require_permission("memory", "write"))
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from xagent.enterprise.auth.dependencies import get_principal
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.rbac import AccessRequest, authorize


def require_permission(resource: str, action: str):
    async def _guard(principal: Principal = Depends(get_principal)) -> Principal:
        if not authorize(principal, AccessRequest(resource=resource, action=action)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权限: {action} on {resource}",
            )
        return principal

    return _guard
