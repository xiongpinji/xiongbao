"""认证路由：登录（签发 JWT）、当前主体信息、OIDC 浏览器登录链路（RFC-002）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from xagent.enterprise.auth import create_access_token
from xagent.enterprise.auth.dependencies import get_principal
from xagent.enterprise.auth.login_rate_limit import get_login_rate_limiter
from xagent.enterprise.auth.oidc_flow import (
    OidcExchangeError,
    OidcNotConfiguredError,
    OidcStateError,
    OidcTokenError,
    build_login_redirect,
    handle_callback,
    oidc_enabled,
)
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
    # True 表示仍在使用默认/初始口令，前端应强制跳转改密
    must_change_password: bool = False


@router.post("/register", summary="注册新用户")
async def register(body: RegisterIn) -> TokenOut:
    store = get_user_store()
    tenant_id = body.tenant_id or body.username
    try:
        await store.aadd(body.username, tenant_id, ["member"], body.password, body.email)
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
    user = await store.aauthenticate(principal.user_id, body.old_password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "旧密码错误")
    await store.achange_password(principal.user_id, body.new_password)
    return {"changed": True, "user_id": principal.user_id}


@router.post("/login", summary="登录签发 JWT")
async def login(body: LoginIn, request: Request) -> TokenOut:
    """登录。

    安全：按 IP+用户名 限流——1 分钟内 5 次失败锁定 60 秒，锁定返回
    429 + retry_after（防口令爆破）。默认口令账号返回 must_change_password=true。
    配置 XAGENT_CACHE__REDIS_URL 后限流状态走 Redis（多实例共享）。
    """
    limiter = get_login_rate_limiter()
    ip = request.client.host if request.client else "unknown"
    key = limiter.make_key(ip, body.username)

    locked = await limiter.alocked_seconds(key)
    if locked > 0:
        retry_after = max(1, int(locked + 0.5))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "login_locked", "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )

    store = get_user_store()
    # bcrypt 校验移入线程池（aauthenticate），避免 ~300ms CPU 阻塞事件循环
    user = await store.aauthenticate(body.username, body.password)
    if user is None:
        # 记录失败；达到阈值后后续请求会被上面的 alocked_seconds 检查拦截
        await limiter.arecord_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")

    await limiter.arecord_success(key)
    tenant_id = body.tenant_id or user.tenant_id
    token = create_access_token(
        user_id=user.user_id, tenant_id=tenant_id, roles=user.roles
    )
    return TokenOut(
        access_token=token, user_id=user.user_id, tenant_id=tenant_id,
        roles=user.roles, must_change_password=user.must_change_password,
    )


@router.get("/me", summary="当前主体")
async def me(principal: Principal = Depends(get_principal)) -> dict:
    return {
        "user_id": principal.user_id,
        "tenant_id": principal.tenant_id,
        "roles": sorted(principal.roles),
        "is_anonymous": principal.is_anonymous,
    }


def _oidc_not_configured(exc: OidcNotConfiguredError) -> HTTPException:
    return HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc))


def _audit_oidc_failure(reason: str) -> None:
    from xagent.enterprise.audit import get_audit_log

    get_audit_log().record(
        tenant_id="default",
        actor="anonymous",
        action="auth.oidc_login_failed",
        resource="auth/oidc/callback",
        detail={"reason": reason},
    )


@router.get("/oidc/providers", summary="OIDC/SSO 可用性（前端据此渲染 SSO 按钮）")
async def oidc_providers() -> dict:
    return {"enabled": oidc_enabled()}


@router.get("/oidc/login", summary="OIDC 登录：302 跳转 IdP 授权端点")
async def oidc_login() -> RedirectResponse:
    try:
        url = await build_login_redirect()
    except OidcNotConfiguredError as exc:
        raise _oidc_not_configured(exc) from exc
    except OidcExchangeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.api_route("/oidc/callback", methods=["GET", "POST"], summary="OIDC 回调：换票 + 签发会话")
async def oidc_callback(
    code: str = "", state: str = "", error: str | None = None
) -> TokenOut:
    """校验 state → 授权码换 token → 验 id_token(JWKS+nonce) → JIT 开户 → TokenOut。"""
    if not oidc_enabled():
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "OIDC 未配置：请设置 XAGENT_SECURITY__OIDC_CLIENT_ID 接 Keycloak",
        )
    if error:
        _audit_oidc_failure(f"idp_error:{error}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"IdP 返回错误: {error}")
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少 code 或 state 参数")
    try:
        result = await handle_callback(code=code, state=state)
    except OidcNotConfiguredError as exc:
        raise _oidc_not_configured(exc) from exc
    except (OidcStateError, OidcTokenError) as exc:
        _audit_oidc_failure(str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except OidcExchangeError as exc:
        _audit_oidc_failure(str(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return TokenOut(**result)
