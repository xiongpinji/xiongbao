"""OIDC Authorization Code Flow（RFC-002）：discovery / login 跳转 / callback 换票。

职责：
- ``discover()``：OIDC discovery（``.well-known/openid-configuration``，5s 超时，
  进程内缓存 1h）；issuer 取 ``oidc_issuer``，缺省从 Keycloak 风格 ``oidc_jwks_url``
  推导（去掉 ``/protocol/openid-connect/certs`` 后缀）。
- ``build_login_redirect()``：生成一次性 ``state``+``nonce``（内存防重放，TTL 10min），
  拼授权端点 302 目标 URL。
- ``handle_callback()``：消费 state（一次性）→ 授权码换 token（client_secret_basic）
  → JWKS/RS256 验 id_token + nonce 比对 → JIT 开户 → 签发 X-Agent JWT 会话 → 审计。

未配置 ``oidc_client_id`` 时抛 ``OidcNotConfiguredError``（路由层转 501），
不影响既有 Bearer 验签链路。
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from xagent.enterprise.auth.jwt_auth import create_access_token
from xagent.enterprise.auth.users import get_user_store
from xagent.infra.logging import get_logger
from xagent.infra.settings import get_settings

logger = get_logger("xagent.oidc")

STATE_TTL_SECONDS = 600  # state/nonce 防重放窗口（RFC-002 §5）
_DISCOVERY_CACHE_TTL = 3600
_HTTP_TIMEOUT = 5.0
# Keycloak JWKS 路径后缀：jwks_url 去掉该后缀即 issuer
_KC_CERTS_SUFFIX = "/protocol/openid-connect/certs"


class OidcNotConfiguredError(Exception):
    """OIDC 未配置（缺 client_id / issuer / jwks_url）。"""


class OidcStateError(Exception):
    """state 无效 / 过期 / 重复使用。"""


class OidcTokenError(Exception):
    """id_token 验签失败 / nonce 不匹配。"""


class OidcExchangeError(Exception):
    """discovery / token 端点网络或协议错误。"""


@dataclass(frozen=True)
class OidcDiscovery:
    authorization_endpoint: str
    token_endpoint: str
    issuer: str = ""


@dataclass
class _StateEntry:
    nonce: str
    expires_at: float


# 内存防重放存储：state -> (nonce, 过期时间)。多实例部署应换共享存储（后续项）。
_states: dict[str, _StateEntry] = {}
# discovery 缓存：issuer -> (discovery, 过期时间)
_discovery_cache: dict[str, tuple[OidcDiscovery, float]] = {}


def reset_oidc_flow() -> None:
    """清空 state 与 discovery 缓存（测试隔离用）。"""
    _states.clear()
    _discovery_cache.clear()


def oidc_enabled() -> bool:
    """OIDC 登录链路是否启用（以 client_id 为准）。"""
    return bool(get_settings().security.oidc_client_id)


def _issuer(sec) -> str:
    if sec.oidc_issuer:
        return sec.oidc_issuer.rstrip("/")
    if sec.oidc_jwks_url:
        url = sec.oidc_jwks_url.rstrip("/")
        if url.endswith(_KC_CERTS_SUFFIX):
            return url[: -len(_KC_CERTS_SUFFIX)]
    raise OidcNotConfiguredError(
        "OIDC 未配置：请设置 XAGENT_SECURITY__OIDC_ISSUER（或 Keycloak 风格 OIDC_JWKS_URL）"
    )


# ─── HTTP 封装（单测 monkeypatch 点）─────────────────────────────────────────


async def _http_get_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def _http_post_form(
    url: str, data: dict[str, str], auth: tuple[str, str]
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(url, data=data, auth=auth)
        resp.raise_for_status()
        return resp.json()


def _get_signing_key(token: str, jwks_url: str) -> Any:
    """从 JWKS 端点取签名公钥（单测 monkeypatch 点）。"""
    return jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key


# ─── discovery ──────────────────────────────────────────────────────────────


async def discover() -> OidcDiscovery:
    """OIDC discovery，带进程内缓存（1h）与 5s 超时。"""
    sec = get_settings().security
    issuer = _issuer(sec)
    cached = _discovery_cache.get(issuer)
    if cached and cached[1] > time.time():
        return cached[0]
    try:
        doc = await _http_get_json(f"{issuer}/.well-known/openid-configuration")
        disc = OidcDiscovery(
            authorization_endpoint=doc["authorization_endpoint"],
            token_endpoint=doc["token_endpoint"],
            issuer=doc.get("issuer", issuer),
        )
    except OidcNotConfiguredError:
        raise
    except Exception as exc:
        raise OidcExchangeError(f"OIDC discovery 失败: {exc}") from exc
    _discovery_cache[issuer] = (disc, time.time() + _DISCOVERY_CACHE_TTL)
    return disc


# ─── state / nonce 防重放 ───────────────────────────────────────────────────


def _purge_expired_states() -> None:
    now = time.time()
    for key in [k for k, v in _states.items() if v.expires_at < now]:
        _states.pop(key, None)


def create_state() -> tuple[str, str]:
    """生成一次性 state + nonce（TTL 10 分钟）。"""
    _purge_expired_states()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    _states[state] = _StateEntry(
        nonce=nonce, expires_at=time.time() + STATE_TTL_SECONDS
    )
    return state, nonce


def consume_state(state: str) -> str:
    """校验并消费 state（一次性），返回绑定的 nonce。"""
    _purge_expired_states()
    entry = _states.pop(state, None)
    if entry is None or entry.expires_at < time.time():
        raise OidcStateError("state 无效、已过期或已被使用")
    return entry.nonce


# ─── login / callback ───────────────────────────────────────────────────────


def _require_configured() -> None:
    if not oidc_enabled():
        raise OidcNotConfiguredError(
            "OIDC 未配置：请设置 XAGENT_SECURITY__OIDC_CLIENT_ID 接 Keycloak"
        )


async def build_login_redirect() -> str:
    """生成 state+nonce，返回 IdP 授权端点 302 目标 URL。"""
    _require_configured()
    sec = get_settings().security
    disc = await discover()
    state, nonce = create_state()
    params = {
        "response_type": "code",
        "client_id": sec.oidc_client_id,
        "redirect_uri": sec.oidc_redirect_uri,
        "scope": sec.oidc_scopes,
        "state": state,
        "nonce": nonce,
    }
    logger.info("oidc_login_redirect", issuer=disc.issuer)
    return f"{disc.authorization_endpoint}?{urlencode(params)}"


def verify_id_token(token: str, *, nonce: str, sec) -> dict[str, Any]:
    """JWKS/RS256 验签 + iss/aud/exp 全校验 + nonce 比对。"""
    try:
        key = _get_signing_key(token, sec.oidc_jwks_url)
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=sec.oidc_client_id,
            issuer=sec.oidc_issuer or None,
            options={
                "require": ["exp", "iat", "sub"],
                "verify_iss": bool(sec.oidc_issuer),
            },
        )
    except Exception as exc:
        raise OidcTokenError(f"id_token 验签失败: {exc}") from exc
    if claims.get("nonce") != nonce:
        raise OidcTokenError("id_token nonce 不匹配")
    return claims


async def _provision_and_session(claims: dict[str, Any], *, issuer: str) -> dict[str, Any]:
    """JIT 开户 + 角色映射 + 签发 X-Agent JWT 会话 + 审计。"""
    from xagent.enterprise.audit import get_audit_log

    user_id = claims.get("preferred_username") or claims.get("sub") or ""
    if not user_id:
        raise OidcTokenError("id_token 缺少 sub")
    tenant_id = claims.get("tenant_id") or "default"
    realm = claims.get("realm_access") or {}
    roles = [str(r) for r in (realm.get("roles") or [])] or ["member"]

    store = get_user_store()
    jit_created = await store.aget(user_id) is None
    if jit_created:
        # 随机口令占位：SSO 用户不走本地口令登录
        await store.aadd(
            user_id,
            tenant_id,
            roles,
            password=secrets.token_urlsafe(24),
            email=claims.get("email", "") or "",
        )
        logger.info("oidc_jit_provisioned", user_id=user_id, tenant_id=tenant_id)

    token = create_access_token(user_id=user_id, tenant_id=tenant_id, roles=roles)
    get_audit_log().record(
        tenant_id=tenant_id,
        actor=user_id,
        action="auth.oidc_login",
        resource="auth/oidc/callback",
        detail={"issuer": issuer, "jit_created": jit_created, "roles": roles},
    )
    return {
        "access_token": token,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "must_change_password": False,
    }


async def handle_callback(*, code: str, state: str) -> dict[str, Any]:
    """回调全流程：state 校验 → 换票 → 验 id_token → JIT → 会话。"""
    _require_configured()
    nonce = consume_state(state)  # 一次性：失败也消费，防重放探测
    sec = get_settings().security
    disc = await discover()
    try:
        token_resp = await _http_post_form(
            disc.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": sec.oidc_redirect_uri,
            },
            auth=(sec.oidc_client_id, sec.oidc_client_secret),  # client_secret_basic
        )
    except Exception as exc:
        raise OidcExchangeError(f"授权码换 token 失败: {exc}") from exc
    id_token = token_resp.get("id_token")
    if not id_token:
        raise OidcExchangeError("token 端点响应缺少 id_token")
    claims = verify_id_token(id_token, nonce=nonce, sec=sec)
    return await _provision_and_session(claims, issuer=disc.issuer)
