"""JWT 签发与校验。HS256（内置）；Keycloak/OIDC 在 Phase 5 接 RS256 验签。

claims 约定：
  sub        -> user_id
  tenant_id  -> 租户（必有）
  roles      -> 角色列表
  scopes     -> 权限范围
  exp/iat    -> 过期/签发
"""

from __future__ import annotations

import time
from typing import Any

import jwt

from xagent.enterprise.auth.principal import Principal
from xagent.infra.settings import get_settings


class InvalidTokenError(Exception):
    """token 缺失 / 过期 / 签名错误。"""


def create_access_token(
    *,
    user_id: str,
    tenant_id: str,
    roles: list[str] | None = None,
    scopes: list[str] | None = None,
    ttl_minutes: int | None = None,
) -> str:
    sec = get_settings().security
    now = int(time.time())
    exp = now + (ttl_minutes or sec.access_token_ttl_minutes) * 60
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "roles": roles or [],
        "scopes": scopes or [],
        "iat": now,
        "exp": exp,
    }
    return jwt.encode(payload, sec.jwt_secret, algorithm=sec.jwt_algorithm)


def decode_token(token: str) -> Principal:
    """校验 token：优先 OIDC(JWKS/RS256)，否则内置 HS256。"""
    sec = get_settings().security
    if sec.oidc_jwks_url:
        principal = _decode_oidc(token, sec)
        if principal is not None:
            return principal
    return _decode_hs256(token, sec)


def _decode_hs256(token: str, sec) -> Principal:
    try:
        claims = jwt.decode(token, sec.jwt_secret, algorithms=[sec.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        raise InvalidTokenError("token 缺少 tenant_id")

    return Principal(
        user_id=claims.get("sub", ""),
        tenant_id=tenant_id,
        roles=frozenset(claims.get("roles", [])),
        scopes=frozenset(claims.get("scopes", [])),
    )


def _decode_oidc(token: str, sec) -> Principal | None:
    """用 Keycloak/OIDC 的 JWKS 验签（RS256）。

    claims 约定：sub=user_id, tenant_id 来自 realm 或自定义 claim；
    roles 来自 resource_access 或 realm_access。
    """
    try:
        from jwt import PyJWKClient

        jwks = PyJWKClient(sec.oidc_jwks_url)
        signing_key = jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=sec.oidc_issuer or None,
            options={"verify_aud": bool(sec.oidc_issuer)},
        )
    except Exception as exc:
        raise InvalidTokenError(f"OIDC 验签失败: {exc}") from exc

    tenant_id = claims.get("tenant_id") or claims.get("realm") or "default"
    # Keycloak 风格：realm_access.roles
    realm = claims.get("realm_access") or {}
    roles = realm.get("roles", [])
    return Principal(
        user_id=claims.get("sub", ""),
        tenant_id=tenant_id,
        roles=frozenset(roles),
        scopes=frozenset(),
    )
