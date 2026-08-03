"""OIDC SSO 链路测试（RFC-002）：login 跳转 / state 防重放 / callback 全流程 /
JIT 开户与角色映射 / 未配置 501。discovery / JWKS / token 交换全部 mock，离线可跑。
"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth import oidc_flow
from xagent.infra.settings import get_settings
from xagent.main import create_app

ISSUER = "https://sso.example.test/realms/xagent"
CLIENT_ID = "xagent-web"
AUTH_EP = f"{ISSUER}/protocol/openid-connect/auth"
TOKEN_EP = f"{ISSUER}/protocol/openid-connect/token"


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_id_token(
    key, *, nonce: str, sub: str = "alice", roles: list[str] | None = None,
    email: str = "", tenant_id: str | None = None,
) -> str:
    now = int(time.time())
    claims: dict = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": sub,
        "preferred_username": sub,
        "iat": now,
        "exp": now + 600,
        "nonce": nonce,
        "email": email,
    }
    if roles is not None:
        claims["realm_access"] = {"roles": roles}
    if tenant_id:
        claims["tenant_id"] = tenant_id
    return pyjwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def oidc_configured(monkeypatch: pytest.MonkeyPatch, rsa_key):
    """配置 OIDC 并 mock discovery / JWKS / token 交换。返回 (rsa_key, http_log)。"""
    monkeypatch.setenv("XAGENT_SECURITY__OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("XAGENT_SECURITY__OIDC_CLIENT_SECRET", "s3cret")
    monkeypatch.setenv("XAGENT_SECURITY__OIDC_ISSUER", ISSUER)
    monkeypatch.setenv(
        "XAGENT_SECURITY__OIDC_JWKS_URL",
        f"{ISSUER}/protocol/openid-connect/certs",
    )
    get_settings.cache_clear()
    oidc_flow.reset_oidc_flow()

    http_log: dict[str, int] = {"discovery": 0, "token": 0}

    async def fake_get_json(url: str) -> dict:
        assert url == f"{ISSUER}/.well-known/openid-configuration"
        http_log["discovery"] += 1
        return {
            "issuer": ISSUER,
            "authorization_endpoint": AUTH_EP,
            "token_endpoint": TOKEN_EP,
        }

    async def fake_post_form(url, data, auth) -> dict:
        assert url == TOKEN_EP
        assert auth == (CLIENT_ID, "s3cret")  # client_secret_basic
        assert data["grant_type"] == "authorization_code"
        http_log["token"] += 1
        return {"id_token": fake_post_form.id_token, "access_token": "at"}

    fake_post_form.id_token = ""  # 测试用例在调用 callback 前设置

    pub_pem = rsa_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    monkeypatch.setattr(oidc_flow, "_http_get_json", fake_get_json)
    monkeypatch.setattr(oidc_flow, "_http_post_form", fake_post_form)
    monkeypatch.setattr(oidc_flow, "_get_signing_key", lambda token, url: pub_pem)

    yield rsa_key, http_log, fake_post_form

    get_settings.cache_clear()
    oidc_flow.reset_oidc_flow()


async def _login_get_state(client: AsyncClient) -> tuple[str, str]:
    """走 login 端点，返回 (state, nonce)。"""
    resp = await client.get("/api/v1/auth/oidc/login")
    assert resp.status_code == 302
    qs = parse_qs(urlparse(resp.headers["location"]).query)
    state = qs["state"][0]
    return state, qs["nonce"][0]


# ─── 未配置 → 501 / providers ───────────────────────────────────────────────


async def test_providers_disabled_by_default(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/oidc/providers")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


async def test_login_501_when_not_configured(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/oidc/login")
    assert resp.status_code == 501
    assert "OIDC_CLIENT_ID" in resp.json()["detail"]


async def test_callback_501_when_not_configured(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": "s"})
    assert resp.status_code == 501


# ─── login 跳转 ─────────────────────────────────────────────────────────────


async def test_login_redirects_to_idp(
    client: AsyncClient, oidc_configured
) -> None:
    resp = await client.get("/api/v1/auth/oidc/login")
    assert resp.status_code == 302
    parsed = urlparse(resp.headers["location"])
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTH_EP
    qs = parse_qs(parsed.query)
    assert qs["response_type"] == ["code"]
    assert qs["client_id"] == [CLIENT_ID]
    assert qs["scope"] == ["openid profile email"]
    assert qs["redirect_uri"] == ["http://localhost:8000/api/v1/auth/oidc/callback"]
    assert qs["state"][0] and qs["nonce"][0]
    # state 已登记且绑定 nonce
    entry = oidc_flow._states[qs["state"][0]]
    assert entry.nonce == qs["nonce"][0]


async def test_discovery_cached(client: AsyncClient, oidc_configured) -> None:
    _, http_log, _ = oidc_configured
    await client.get("/api/v1/auth/oidc/login")
    await client.get("/api/v1/auth/oidc/login")
    assert http_log["discovery"] == 1  # 第二次命中缓存


# ─── state 防重放 ───────────────────────────────────────────────────────────


async def test_callback_wrong_state_400(client: AsyncClient, oidc_configured) -> None:
    resp = await client.get(
        "/api/v1/auth/oidc/callback", params={"code": "x", "state": "forged"}
    )
    assert resp.status_code == 400
    assert "state" in resp.json()["detail"]


async def test_callback_state_replay_400(client: AsyncClient, oidc_configured) -> None:
    key, _, post_mock = oidc_configured
    state, nonce = await _login_get_state(client)
    post_mock.id_token = _make_id_token(key, nonce=nonce)
    params = {"code": "authcode", "state": state}
    first = await client.get("/api/v1/auth/oidc/callback", params=params)
    assert first.status_code == 200
    # 同一 state 重放 → 一次性消费，拒绝
    replay = await client.get("/api/v1/auth/oidc/callback", params=params)
    assert replay.status_code == 400


# ─── callback 全流程 ────────────────────────────────────────────────────────


async def test_callback_full_flow_jit_roles_audit(
    client: AsyncClient, oidc_configured
) -> None:
    key, http_log, post_mock = oidc_configured
    state, nonce = await _login_get_state(client)
    post_mock.id_token = _make_id_token(
        key, nonce=nonce, sub="alice", roles=["member", "analyst"],
        email="alice@corp.example", tenant_id="tenant-a",
    )
    resp = await client.get(
        "/api/v1/auth/oidc/callback", params={"code": "authcode", "state": state}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "alice"
    assert body["tenant_id"] == "tenant-a"
    assert set(body["roles"]) == {"member", "analyst"}
    assert body["must_change_password"] is False
    assert http_log["token"] == 1

    # 会话 token 是有效 X-Agent JWT（HS256，claims 映射正确）
    sec = get_settings().security
    claims = pyjwt.decode(
        body["access_token"], sec.jwt_secret, algorithms=[sec.jwt_algorithm]
    )
    assert claims["sub"] == "alice"
    assert claims["tenant_id"] == "tenant-a"
    assert set(claims["roles"]) == {"member", "analyst"}

    # JIT 开户：用户已落库
    from xagent.enterprise.auth.users import get_user_store

    user = get_user_store().get("alice")
    assert user is not None
    assert user.tenant_id == "tenant-a"
    assert user.email == "alice@corp.example"

    # 审计事件 auth.oidc_login
    from xagent.enterprise.audit import get_audit_log

    actions = [e.action for e in get_audit_log().list()]
    assert "auth.oidc_login" in actions


async def test_callback_default_member_role(
    client: AsyncClient, oidc_configured
) -> None:
    key, _, post_mock = oidc_configured
    state, nonce = await _login_get_state(client)
    post_mock.id_token = _make_id_token(key, nonce=nonce, sub="bob", roles=None)
    resp = await client.get(
        "/api/v1/auth/oidc/callback", params={"code": "c", "state": state}
    )
    assert resp.status_code == 200
    assert resp.json()["roles"] == ["member"]
    assert resp.json()["tenant_id"] == "default"


async def test_callback_via_post(client: AsyncClient, oidc_configured) -> None:
    key, _, post_mock = oidc_configured
    state, nonce = await _login_get_state(client)
    post_mock.id_token = _make_id_token(key, nonce=nonce, sub="carol", roles=["member"])
    resp = await client.post(
        "/api/v1/auth/oidc/callback", params={"code": "c", "state": state}
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "carol"


async def test_callback_nonce_mismatch_400(
    client: AsyncClient, oidc_configured
) -> None:
    key, _, post_mock = oidc_configured
    state, _ = await _login_get_state(client)
    post_mock.id_token = _make_id_token(key, nonce="attacker-nonce")
    resp = await client.get(
        "/api/v1/auth/oidc/callback", params={"code": "c", "state": state}
    )
    assert resp.status_code == 400
    assert "nonce" in resp.json()["detail"]


async def test_callback_bad_signature_400(client: AsyncClient, oidc_configured) -> None:
    _, _, post_mock = oidc_configured
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    state, nonce = await _login_get_state(client)
    post_mock.id_token = _make_id_token(other_key, nonce=nonce)
    resp = await client.get(
        "/api/v1/auth/oidc/callback", params={"code": "c", "state": state}
    )
    assert resp.status_code == 400
