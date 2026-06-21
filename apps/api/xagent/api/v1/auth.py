"""认证路由：登录（签发 JWT）、当前主体信息、OIDC 回调占位。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from xagent.enterprise.auth import create_access_token
from xagent.enterprise.auth.dependencies import get_principal
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.auth.users import get_user_store

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    tenant_id: str | None = None  # 不填用用户所属租户


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    email: str = ""
    tenant_id: str | None = None  # 不填则用户名作为租户（多租户自服务）


class ChangePasswordIn(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    user_id: str
    tenant_id: str
    roles: list[str]


@router.post("/register", summary="注册新用户")
async def register(body: RegisterIn) -> TokenOut:
    store = get_user_store()
    tenant_id = body.tenant_id or body.username
    try:
        store.add(body.username, tenant_id, ["member"], body.password, body.email)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在") from exc
    token = create_access_token(
        user_id=body.username, tenant_id=tenant_id, roles=["member"]
    )
    return TokenOut(
        access_token=token, user_id=body.username, tenant_id=tenant_id, roles=["member"]
    )


@router.post("/change-password", summary="修改密码")
async def change_password(
    body: ChangePasswordIn,
    principal: Principal = Depends(get_principal),
) -> dict:
    store = get_user_store()
    user = store.authenticate(principal.user_id, body.old_password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "旧密码错误")
    store.change_password(principal.user_id, body.new_password)
    return {"changed": True, "user_id": principal.user_id}


@router.post("/login", summary="登录签发 JWT")
async def login(body: LoginIn) -> TokenOut:
    store = get_user_store()
    user = store.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    tenant_id = body.tenant_id or user.tenant_id
    token = create_access_token(
        user_id=user.user_id, tenant_id=tenant_id, roles=user.roles
    )
    return TokenOut(
        access_token=token, user_id=user.user_id, tenant_id=tenant_id, roles=user.roles
    )


@router.get("/me", summary="当前主体")
async def me(principal: Principal = Depends(get_principal)) -> dict:
    return {
        "user_id": principal.user_id,
        "tenant_id": principal.tenant_id,
        "roles": sorted(principal.roles),
        "is_anonymous": principal.is_anonymous,
    }


@router.post("/oidc/callback", summary="OIDC 回调（占位，接 Keycloak 时启用）")
async def oidc_callback(code: str) -> dict:
    """配置 XAGENT_SECURITY__OIDC_JWKS_URL 后，此处用 code 换 token 并验签。"""
    _ = code
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "OIDC 未配置：请设置 XAGENT_SECURITY__OIDC_JWKS_URL 接 Keycloak",
    )
