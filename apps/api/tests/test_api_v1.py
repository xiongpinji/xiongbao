"""API v1 集成测试：鉴权强制、越权回归、租户隔离、agent run、审计。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth import create_access_token
from xagent.infra.settings import get_settings
from xagent.main import create_app


@pytest.fixture
async def app_client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_lite_anonymous_blocked_by_default(app_client: AsyncClient) -> None:
    # 安全默认：lite 默认 require_auth=True -> 匿名访问受保护端点 401
    resp = await app_client.get("/api/v1/agents/roles")
    assert resp.status_code == 401


async def test_require_auth_escape_hatch_allows_anonymous(app_client: AsyncClient) -> None:
    # 显式逃生门：require_auth=False 后匿名可访问公开端点（无角色依赖），
    # 但匿名 Principal 为空角色，受权限保护的端点（如 /agents/roles 需 agent:read）仍 403
    get_settings().security.require_auth = False
    try:
        resp = await app_client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["is_anonymous"] is True
        resp = await app_client.get("/api/v1/agents/roles")
        assert resp.status_code == 403
    finally:
        get_settings().security.require_auth = None


async def test_require_auth_blocks_anonymous(app_client: AsyncClient, monkeypatch) -> None:
    # 打开 require_auth 后，无 token 应 401
    get_settings().security.require_auth = True
    try:
        resp = await app_client.get("/api/v1/agents/roles")
        assert resp.status_code == 401
    finally:
        get_settings().security.require_auth = None


async def test_tenant_mismatch_forbidden(app_client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="tenantA", roles=["member"])
    # 声明 X-Tenant-Id 与 token 不一致 -> 403（越权防护）
    resp = await app_client.get(
        "/api/v1/agents/roles",
        headers={**_auth(token), "X-Tenant-Id": "tenantB"},
    )
    assert resp.status_code == 403


async def test_viewer_cannot_execute_agent(app_client: AsyncClient) -> None:
    token = create_access_token(user_id="v", tenant_id="t1", roles=["viewer"])
    resp = await app_client.post(
        "/api/v1/agents/run", json={"goal": "hi"}, headers=_auth(token)
    )
    assert resp.status_code == 403


async def test_member_can_run_agent(app_client: AsyncClient) -> None:
    token = create_access_token(user_id="m", tenant_id="t1", roles=["member"])
    resp = await app_client.post(
        "/api/v1/agents/run",
        json={"goal": "用一句话介绍 X-Agent"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_answer"]
    assert body["tenant_id"] == "t1"
    assert body["events"]


async def test_memory_tenant_isolation(app_client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["member"])

    # 租户 A 写入
    w = await app_client.post(
        "/api/v1/memory",
        json={"items": [{"id": "secret", "text": "租户A机密资料"}]},
        headers=_auth(token_a),
    )
    assert w.status_code == 200

    # 租户 B 检索，不应看到 A 的数据
    s = await app_client.post(
        "/api/v1/memory/search",
        json={"query": "机密资料", "top_k": 10},
        headers=_auth(token_b),
    )
    assert s.status_code == 200
    ids = {h["id"] for h in s.json()["hits"]}
    assert "secret" not in ids

    # 租户 A 自己能检到
    s2 = await app_client.post(
        "/api/v1/memory/search",
        json={"query": "机密资料", "top_k": 10},
        headers=_auth(token_a),
    )
    assert "secret" in {h["id"] for h in s2.json()["hits"]}


async def test_memory_write_cannot_inject_foreign_tenant(app_client: AsyncClient) -> None:
    token = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    # 尝试在 metadata 注入别的 tenant_id -> 必须被覆盖为 tA
    await app_client.post(
        "/api/v1/memory",
        json={"items": [{"id": "x", "text": "数据", "metadata": {"tenant_id": "tEVIL"}}]},
        headers=_auth(token),
    )
    # 用 tEVIL 检索不到（因为实际写入的是 tA）
    token_evil = create_access_token(user_id="e", tenant_id="tEVIL", roles=["member"])
    s = await app_client.post(
        "/api/v1/memory/search",
        json={"query": "数据", "top_k": 10},
        headers=_auth(token_evil),
    )
    assert "x" not in {h["id"] for h in s.json()["hits"]}
