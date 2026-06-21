"""Phase 5 企业硬化测试：登录/计费/配额/审计导出/越权。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.domains.billing import get_billing_service
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_login_default_admin(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert "admin" in body["roles"]
    assert body["user_id"] == "admin"


async def test_login_wrong_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert resp.status_code == 401


async def test_me_endpoint(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.get("/api/v1/auth/me", headers=_h(token))
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "u"


async def test_billing_summary(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.get("/api/v1/billing/summary", headers=_h(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"] == "free"
    assert body["usage"]["agent_runs"] == 0


async def test_billing_set_plan_admin_only(client: AsyncClient) -> None:
    member = create_access_token(user_id="m", tenant_id="t1", roles=["member"])
    admin = create_access_token(user_id="a", tenant_id="t1", roles=["admin"])
    # member 不能改档
    r1 = await client.post(
        "/api/v1/billing/plan", json={"plan": "pro"}, headers=_h(member)
    )
    assert r1.status_code == 403
    # admin 可以
    r2 = await client.post(
        "/api/v1/billing/plan", json={"plan": "pro"}, headers=_h(admin)
    )
    assert r2.status_code == 200
    assert r2.json()["plan"] == "pro"


async def test_agent_run_consumes_quota(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    await client.post(
        "/api/v1/agents/run", json={"goal": "hi"}, headers=_h(token)
    )
    s = (await client.get("/api/v1/billing/summary", headers=_h(token))).json()
    assert s["usage"]["agent_runs"] == 1


async def test_quota_exceeded_returns_402(client: AsyncClient) -> None:
    # 把 free 配额耗尽
    svc = get_billing_service()
    for _ in range(100):
        svc.check_and_consume("tQ", actor="u", action="agent.run")
    token = create_access_token(user_id="u", tenant_id="tQ", roles=["member"])
    resp = await client.post(
        "/api/v1/agents/run", json={"goal": "hi"}, headers=_h(token)
    )
    assert resp.status_code == 402


async def test_audit_export_and_verify(client: AsyncClient) -> None:
    admin = create_access_token(user_id="a", tenant_id="t1", roles=["admin"])
    # 触发一次审计写入
    await client.post(
        "/api/v1/agents/run", json={"goal": "hi"}, headers=_h(admin)
    )
    v = await client.get("/api/v1/audit/verify", headers=_h(admin))
    assert v.status_code == 200
    assert v.json()["valid"] is True

    exp = await client.get("/api/v1/audit/export", headers=_h(admin))
    assert exp.status_code == 200
    assert "integrity" in exp.text


async def test_audit_member_cannot_export_full(client: AsyncClient) -> None:
    member = create_access_token(user_id="m", tenant_id="t1", roles=["member"])
    resp = await client.get("/api/v1/audit/export-full", headers=_h(member))
    assert resp.status_code == 403  # audit:manage 仅 admin
