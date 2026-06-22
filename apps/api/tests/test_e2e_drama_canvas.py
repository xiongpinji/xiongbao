"""端到端冒烟：短剧工厂 → 画布 → 工作流 → 媒体 → 剪辑 → 导出 全链路。"""

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


async def test_drama_canvas_end_to_end(client: AsyncClient) -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", roles=["admin"])

    # 1) 创建画布
    canvas_resp = await client.post(
        "/api/v1/canvas",
        json={"title": "E2E 短剧", "brief": "都市重生爽文"},
        headers=_auth(token),
    )
    assert canvas_resp.status_code == 200, canvas_resp.text
    canvas = canvas_resp.json()
    canvas_id = canvas["canvas_id"]
    first_node = canvas["nodes"][0]["node_id"]

    # 2) 追加分镜节点 + 保存 layout（A -> B）
    storyboard_resp = await client.post(
        f"/api/v1/canvas/{canvas_id}/nodes",
        json={"node_type": "分镜", "title": "分镜"},
        headers=_auth(token),
    )
    storyboard_id = storyboard_resp.json()["nodes"][-1]["node_id"]
    layout_resp = await client.put(
        f"/api/v1/canvas/{canvas_id}/layout",
        json={
            "nodes": [
                {"node_id": first_node, "position": {"x": 80, "y": 120}},
                {"node_id": storyboard_id, "position": {"x": 380, "y": 120}},
            ],
            "edges": [{"source": first_node, "target": storyboard_id}],
        },
        headers=_auth(token),
    )
    assert layout_resp.status_code == 200
    by_id = {n["node_id"]: n for n in layout_resp.json()["nodes"]}
    assert by_id[storyboard_id]["dependencies"] == [first_node]

    # 3) 触发整张画布工作流
    run_resp = await client.post(f"/api/v1/canvas/{canvas_id}/run", headers=_auth(token))
    assert run_resp.status_code == 200, run_resp.text
    run_payload = run_resp.json()
    assert run_payload["workflow_run_id"]
    assert any(step.get("has_approval") for step in run_payload["workflow"]["steps"])

    # 4) 单节点重跑（分镜）
    step_resp = await client.post(
        f"/api/v1/canvas/{canvas_id}/run/{storyboard_id}",
        headers=_auth(token),
    )
    assert step_resp.status_code == 200
    assert step_resp.json()["node_id"] == storyboard_id

    # 5) 媒体生成 + 轮询
    media_resp = await client.post(
        "/api/v1/creative-studio/media/generate",
        json={"kind": "image", "mode": "text_to_image", "prompt": "海边日落", "wait": False},
        headers=_auth(token),
    )
    assert media_resp.status_code == 200
    task_id = media_resp.json()["task_id"]
    poll_resp = await client.get(
        f"/api/v1/creative-studio/media/tasks/{task_id}",
        headers=_auth(token),
    )
    assert poll_resp.status_code == 200
    assert poll_resp.json()["task_id"] == task_id

    # 6) 创建 timeline，添加 clip + 转场（导出/渲染依赖真实视频文件，由专用测试覆盖）
    tl_resp = await client.post(
        "/api/v1/creative-studio/editor/timelines",
        json={"name": "E2E timeline"},
        headers=_auth(token),
    )
    assert tl_resp.status_code == 200
    timeline_id = tl_resp.json()["id"]
    add_clip_resp = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{timeline_id}/clips",
        json={
            "track_type": "video",
            "source_url": "local://renders/sample.mp4",
            "timeline_start": 0,
            "timeline_end": 5,
            "duration": 5,
        },
        headers=_auth(token),
    )
    assert add_clip_resp.status_code == 200
    clip_id = add_clip_resp.json()["clips"][-1]["id"]
    trans_resp = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{timeline_id}/transitions",
        json={"clip_id": clip_id, "type": "fade", "duration": 0.5},
        headers=_auth(token),
    )
    assert trans_resp.status_code == 200
    trans_payload = trans_resp.json()
    assert any(t["clip_id"] == clip_id for t in trans_payload["transitions"])

    # 7) 系统能力可读
    caps = await client.get("/api/v1/system/capabilities", headers=_auth(token))
    assert caps.status_code == 200
    assert caps.json()["tenant"] == "t1"
