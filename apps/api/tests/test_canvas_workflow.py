"""画布 layout / run / workflow 对齐 测试。"""

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


async def _create_canvas(client: AsyncClient, token: str) -> dict:
    resp = await client.post(
        "/api/v1/canvas",
        json={"title": "测试画布", "brief": ""},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_save_layout_translates_edges_to_dependencies(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["member"])
    canvas = await _create_canvas(client, token)

    add_a = await client.post(
        f"/api/v1/canvas/{canvas['canvas_id']}/nodes",
        json={"node_type": "梗概", "title": "梗概"},
        headers=_auth(token),
    )
    add_b = await client.post(
        f"/api/v1/canvas/{canvas['canvas_id']}/nodes",
        json={"node_type": "分镜", "title": "分镜"},
        headers=_auth(token),
    )
    node_a_id = add_a.json()["nodes"][-1]["node_id"]
    node_b_id = add_b.json()["nodes"][-1]["node_id"]

    layout = await client.put(
        f"/api/v1/canvas/{canvas['canvas_id']}/layout",
        json={
            "nodes": [
                {"node_id": node_a_id, "position": {"x": 80, "y": 120}},
                {"node_id": node_b_id, "position": {"x": 360, "y": 120}},
            ],
            "edges": [{"source": node_a_id, "target": node_b_id}],
        },
        headers=_auth(token),
    )
    assert layout.status_code == 200, layout.text
    nodes = {n["node_id"]: n for n in layout.json()["nodes"]}
    assert nodes[node_b_id]["dependencies"] == [node_a_id]
    assert nodes[node_a_id]["position"]["x"] == 80


async def test_run_canvas_creates_workflow_run_and_handles_approval(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["admin"])
    canvas = await _create_canvas(client, token)
    # 默认仅含一个“需求分析”节点
    canvas_id = canvas["canvas_id"]

    run_resp = await client.post(
        f"/api/v1/canvas/{canvas_id}/run",
        headers=_auth(token),
    )
    assert run_resp.status_code == 200, run_resp.text
    payload = run_resp.json()
    assert payload["canvas_id"] == canvas_id
    assert payload["workflow_run_id"]
    assert payload["workflow"]["status"] in {"awaiting_approval", "completed", "failed"}
    # 需求分析节点应被标记为审核门
    has_approval = any(step.get("has_approval") for step in payload["workflow"]["steps"])
    assert has_approval


async def test_run_canvas_requires_nodes(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["admin"])
    canvas = await _create_canvas(client, token)
    canvas_id = canvas["canvas_id"]
    # 清空默认节点
    from xagent.api.v1 import canvas as _cv

    _cv._canvases[canvas_id].nodes.clear()
    resp = await client.post(
        f"/api/v1/canvas/{canvas_id}/run",
        headers=_auth(token),
    )
    assert resp.status_code == 400


async def test_canvas_tenant_isolation_for_layout(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["member"])
    canvas = await _create_canvas(client, token_a)
    resp = await client.put(
        f"/api/v1/canvas/{canvas['canvas_id']}/layout",
        json={"nodes": [], "edges": []},
        headers=_auth(token_b),
    )
    assert resp.status_code in (403, 404)


async def test_run_canvas_step_executes_single_node(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["admin"])
    canvas = await _create_canvas(client, token)
    canvas_id = canvas["canvas_id"]
    node_id = canvas["nodes"][0]["node_id"]
    resp = await client.post(
        f"/api/v1/canvas/{canvas_id}/run/{node_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["node_id"] == node_id
    assert payload["workflow"]["status"] in {"completed", "failed", "rolled_back"}
    # 节点 agent_note 应当被回写
    updated = next(n for n in payload["canvas"]["nodes"] if n["node_id"] == node_id)
    assert updated["agent_note"]


async def test_run_canvas_step_404_for_missing_node(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["admin"])
    canvas = await _create_canvas(client, token)
    resp = await client.post(
        f"/api/v1/canvas/{canvas['canvas_id']}/run/does-not-exist",
        headers=_auth(token),
    )
    assert resp.status_code == 404
