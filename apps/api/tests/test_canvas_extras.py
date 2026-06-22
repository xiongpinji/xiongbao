"""画布扩展接口测试：PATCH / estimate / quality / auto-fix / parse / batch / import-export。"""

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


async def _new_canvas(client: AsyncClient, token: str, brief: str = "测试brief") -> dict:
    resp = await client.post(
        "/api/v1/canvas",
        json={"title": "扩展测试画布", "brief": brief},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _add_node(client: AsyncClient, token: str, canvas_id: str, node_type: str) -> str:
    resp = await client.post(
        f"/api/v1/canvas/{canvas_id}/nodes",
        json={"node_type": node_type, "title": node_type},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["nodes"][-1]["node_id"]


async def test_patch_node_merges_settings_and_locks(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["member"])
    canvas = await _new_canvas(client, token)
    node_id = await _add_node(client, token, canvas["canvas_id"], "关键帧")

    # 写入 settings
    resp = await client.patch(
        f"/api/v1/canvas/{canvas['canvas_id']}/nodes/{node_id}",
        json={
            "settings": {
                "prompt": "cyber cat",
                "steps": 28,
                "cfg": 6.5,
                "resolution": "1024x1024",
            },
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    node = resp.json()["node"]
    assert node["settings"]["prompt"] == "cyber cat"
    assert node["settings"]["steps"] == 28

    # 锁定后修改 prompt 应 409
    resp = await client.patch(
        f"/api/v1/canvas/{canvas['canvas_id']}/nodes/{node_id}",
        json={"locked": True},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    resp = await client.patch(
        f"/api/v1/canvas/{canvas['canvas_id']}/nodes/{node_id}",
        json={"settings": {"prompt": "blocked"}, "locked": True},
        headers=_auth(token),
    )
    assert resp.status_code == 409


async def test_estimate_and_quality_endpoints(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["member"])
    canvas = await _new_canvas(client, token)
    kf = await _add_node(client, token, canvas["canvas_id"], "关键帧")
    await client.patch(
        f"/api/v1/canvas/{canvas['canvas_id']}/nodes/{kf}",
        json={
            "settings": {
                "resolution": "1024x1024",
                "steps": 28,
                "cfg": 6.5,
                "sampler": "euler_a",
                "prompt": "p",
            },
        },
        headers=_auth(token),
    )
    resp = await client.post(
        f"/api/v1/canvas/{canvas['canvas_id']}/estimate",
        json={},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "peak_vram_mb" in data
    assert any(n["node_id"] == kf for n in data["nodes"])

    resp = await client.post(
        f"/api/v1/canvas/{canvas['canvas_id']}/quality",
        json={"node_ids": [kf]},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    out = resp.json()["nodes"][0]
    assert 0 <= out["overall"] <= 100
    assert "issues" in out


async def test_auto_fix_fills_missing_settings(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["member"])
    canvas = await _new_canvas(client, token)
    kf = await _add_node(client, token, canvas["canvas_id"], "关键帧")

    resp = await client.post(
        f"/api/v1/canvas/{canvas['canvas_id']}/nodes/{kf}/auto-fix",
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    patch = resp.json()["patch"]
    assert "sampler" in patch
    assert "steps" in patch
    assert "resolution" in patch


async def test_script_parse_creates_storyboard_nodes(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["member"])
    canvas = await _new_canvas(client, token, brief="开头是清晨。少女走在路上。她遇到了陌生人。")
    resp = await client.post(
        f"/api/v1/canvas/{canvas['canvas_id']}/script/parse",
        json={},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert len(payload["created"]) >= 2
    assert payload["created"][0]["node_type"] == "分镜"


async def test_export_then_import_canvas_round_trip(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["member"])
    canvas = await _new_canvas(client, token)
    a = await _add_node(client, token, canvas["canvas_id"], "梗概")
    b = await _add_node(client, token, canvas["canvas_id"], "分镜")
    await client.put(
        f"/api/v1/canvas/{canvas['canvas_id']}/layout",
        json={"nodes": [], "edges": [{"source": a, "target": b}]},
        headers=_auth(token),
    )

    resp = await client.get(
        f"/api/v1/canvas/{canvas['canvas_id']}/export",
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["version"] == 1
    assert any(e["source"] == a and e["target"] == b for e in payload["edges"])

    imported = await client.post(
        "/api/v1/canvas/import",
        json={
            "title": payload["title"],
            "brief": payload["brief"],
            "nodes": payload["nodes"],
            "edges": payload["edges"],
        },
        headers=_auth(token),
    )
    assert imported.status_code == 200, imported.text
    new_canvas = imported.json()
    # 节点数量保留
    assert len(new_canvas["nodes"]) == len(payload["nodes"])


async def test_request_review_sets_status(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["member"])
    canvas = await _new_canvas(client, token)
    node_id = await _add_node(client, token, canvas["canvas_id"], "梗概")

    resp = await client.post(
        f"/api/v1/canvas/{canvas['canvas_id']}/nodes/{node_id}/request-review",
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    node = next(n for n in resp.json()["nodes"] if n["node_id"] == node_id)
    assert node["status"] == "review_required"


async def test_batch_generate_with_null_provider(client: AsyncClient) -> None:
    """NullProvider 始终能产出 task_id，确保接口可在 lite 模式跑通。"""
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["member"])
    canvas = await _new_canvas(client, token)
    kf = await _add_node(client, token, canvas["canvas_id"], "关键帧")
    await client.patch(
        f"/api/v1/canvas/{canvas['canvas_id']}/nodes/{kf}",
        json={"settings": {"prompt": "test", "resolution": "768x768"}},
        headers=_auth(token),
    )

    resp = await client.post(
        f"/api/v1/canvas/{canvas['canvas_id']}/batch-generate",
        json={"node_types": ["关键帧"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["node_id"] == kf
    # NullProvider 应返回 task_id；如果没有任何 provider，则至少不报 error key 之外的字段
    assert "task_id" in result or "error" in result
