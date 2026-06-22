"""系统能力概览接口测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_capabilities_returns_real_metadata(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["admin"])
    resp = await client.get("/api/v1/system/capabilities", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["tenant"] == "t1"
    assert isinstance(payload["tools"], list)
    assert isinstance(payload["mcp_servers"], list)
    assert any(cmd["name"] == "/new" for cmd in payload["commands"])
    assert payload["code_preview"]["tab_size"] == 2
    assert payload["onboarding"]
