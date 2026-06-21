"""FastAPI 鉴权依赖：统一产出 Principal，强制租户一致性。

规则：
- 带 Bearer token：校验 JWT -> Principal。无效 -> 401。
- 无 token：
    require_auth=True  -> 401（full/enterprise）
    require_auth=False -> 匿名 Principal（lite 演示）
- 若请求带 X-Tenant-Id 头，必须与 principal.tenant_id 一致，否则 403（防越权）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from xagent.enterprise.auth.jwt_auth import InvalidTokenError, decode_token
from xagent.enterprise.auth.principal import Principal
from xagent.infra.settings import get_settings


async def get_principal(
    authorization: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> Principal:
    settings = get_settings()
    principal: Principal | None = None

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization 头格式应为 'Bearer <token>'",
            )
        try:
            principal = decode_token(token)
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"无效 token: {exc}",
            ) from exc

    if principal is None:
        if settings.auth_required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少认证凭据",
            )
        principal = Principal.anonymous()

    # 租户一致性校验：请求头声明的租户必须等于 token 租户（防跨租户越权）
    if x_tenant_id and x_tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="租户不匹配：禁止跨租户访问",
        )

    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_role(role: str):
    """生成一个要求特定角色的依赖。"""

    async def _checker(principal: PrincipalDep) -> Principal:
        if not principal.has_role(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要角色: {role}",
            )
        return principal

    return _checker
