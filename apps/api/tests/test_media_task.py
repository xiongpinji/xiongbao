"""media task 轮询接口测试。"""

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


async def test_media_task_returns_status_for_owner(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["admin"])
    resp = await client.post(
        "/api/v1/creative-studio/media/generate",
        json={"kind": "image", "mode": "text_to_image", "prompt": "天空", "wait": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["task_id"]
    assert task_id

    poll = await client.get(
        f"/api/v1/creative-studio/media/tasks/{task_id}",
        headers=_auth(token),
    )
    assert poll.status_code == 200, poll.text
    body = poll.json()
    assert body["task_id"] == task_id
    assert body["kind"] == "image"
    assert body["status"] in {"succeeded", "running", "pending", "failed"}


async def test_media_task_isolated_across_tenants(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["admin"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["admin"])
    resp = await client.post(
        "/api/v1/creative-studio/media/generate",
        json={"kind": "image", "mode": "text_to_image", "prompt": "海", "wait": False},
        headers=_auth(token_a),
    )
    task_id = resp.json()["task_id"]
    poll = await client.get(
        f"/api/v1/creative-studio/media/tasks/{task_id}",
        headers=_auth(token_b),
    )
    assert poll.status_code in (403, 404)
