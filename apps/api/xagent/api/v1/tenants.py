"""租户 + 用户 + API Key 管理路由。仅 admin 可操作。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xagent.enterprise.auth.api_keys import get_api_key_store
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.auth.users import UserExistsError, get_user_store
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/tenants", tags=["tenants"])


# ─── 用户管理 ───

class UserCreateIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    roles: list[str] = Field(default_factory=lambda: ["member"])
    email: str = ""


class UserRoleIn(BaseModel):
    roles: list[str]


@router.get("/users", summary="列出当前租户用户")
async def list_users(principal: Principal = Depends(require_permission("system", "manage"))) -> dict:
    store = get_user_store()
    users = [
        {"user_id": u.user_id, "tenant_id": u.tenant_id, "roles": u.roles, "email": u.email}
        for u in store._users.values()
        if u.tenant_id == principal.tenant_id
    ]
    return {"users": users, "count": len(users)}


@router.post("/users", summary="创建用户（admin）")
async def create_user(
    body: UserCreateIn,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    store = get_user_store()
    try:
        u = store.add(body.username, principal.tenant_id, body.roles, body.password, body.email)
    except UserExistsError as exc:
        raise HTTPException(409, "用户名已存在") from exc
    return {"user_id": u.user_id, "tenant_id": u.tenant_id, "roles": u.roles}


@router.put("/users/{user_id}/roles", summary="修改用户角色")
async def update_user_roles(
    user_id: str,
    body: UserRoleIn,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    store = get_user_store()
    u = store.get(user_id)
    if not u or u.tenant_id != principal.tenant_id:
        raise HTTPException(404, "用户不存在")
    # 重建用户（dataclass 不可变）
    from xagent.enterprise.auth.users import User
    store._users[user_id] = User(
        user_id=u.user_id, tenant_id=u.tenant_id, roles=body.roles,
        password_hash=u.password_hash, email=u.email,
    )
    return {"user_id": user_id, "roles": body.roles}


@router.delete("/users/{user_id}", summary="删除用户")
async def delete_user(
    user_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    store = get_user_store()
    u = store.get(user_id)
    if not u or u.tenant_id != principal.tenant_id:
        raise HTTPException(404, "用户不存在")
    if user_id == principal.user_id:
        raise HTTPException(400, "不能删除自己")
    del store._users[user_id]
    return {"deleted": user_id}


# ─── API Key 管理 ───

class ApiKeyCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=lambda: ["*"])
    expires_at: str | None = None


@router.get("/api-keys", summary="列出当前租户 API Key")
async def list_api_keys(
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    store = get_api_key_store()
    keys = [k.to_view() for k in store.list_keys(principal.tenant_id)]
    return {"keys": keys, "count": len(keys)}


@router.post("/api-keys", summary="创建 API Key（返回原始 key 仅此一次）")
async def create_api_key(
    body: ApiKeyCreateIn,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    store = get_api_key_store()
    ak, raw = store.create(
        tenant_id=principal.tenant_id,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )
    return {"key": ak.to_view(), "raw_key": raw, "warning": "raw_key 仅显示一次，请妥善保存"}


@router.post("/api-keys/{key_id}/revoke", summary="吊销 API Key")
async def revoke_api_key(
    key_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    store = get_api_key_store()
    if not store.revoke(key_id, principal.tenant_id):
        raise HTTPException(404, "Key 不存在")
    return {"revoked": key_id}


@router.delete("/api-keys/{key_id}", summary="删除 API Key")
async def delete_api_key(
    key_id: str,
    principal: Principal = Depends(require_permission("system", "manage")),
) -> dict:
    store = get_api_key_store()
    if not store.delete(key_id, principal.tenant_id):
        raise HTTPException(404, "Key 不存在")
    return {"deleted": key_id}


# ─── 租户信息 ───

@router.get("/info", summary="当前租户信息")
async def tenant_info(principal: Principal = Depends(require_permission("system", "read"))) -> dict:
    store = get_user_store()
    user_count = sum(1 for u in store._users.values() if u.tenant_id == principal.tenant_id)
    key_store = get_api_key_store()
    key_count = len(key_store.list_keys(principal.tenant_id))
    return {
        "tenant_id": principal.tenant_id,
        "user_count": user_count,
        "api_key_count": key_count,
        "roles_available": ["admin", "member", "viewer"],
    }
