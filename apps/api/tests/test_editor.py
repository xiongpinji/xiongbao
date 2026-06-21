"""视频剪辑引擎测试：时间线 CRUD + 片段/转场 + 渲染降级 + 草稿导出 + 工具。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.domains.creative_studio.editor.models import (
    Clip,
    Timeline,
    TrackType,
)
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- 数据模型 ----


def test_timeline_model() -> None:
    tl = Timeline(name="test", width=1080, height=1920, fps=30)
    assert tl.total_duration == 0
    tl.add_clip(Clip(track_type=TrackType.video, timeline_start=0, timeline_end=5))
    tl.add_clip(Clip(track_type=TrackType.text, text="你好", timeline_start=1, timeline_end=3))
    assert tl.total_duration == 5
    d = tl.to_dict()
    assert len(d["clips"]) == 2
    assert d["clips"][1]["text"] == "你好"


def test_clip_remove() -> None:
    tl = Timeline()
    c1 = tl.add_clip(Clip(timeline_end=3))
    c2 = tl.add_clip(Clip(timeline_end=5))
    assert len(tl.clips) == 2
    assert tl.remove_clip(c1.id)
    assert len(tl.clips) == 1
    assert tl.clips[0].id == c2.id


# ---- API ----


async def test_create_timeline(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post(
        "/api/v1/creative-studio/editor/timelines",
        json={"name": "短剧1", "width": 1080, "height": 1920},
        headers=_h(token),
    )
    assert resp.status_code == 200
    tl = resp.json()
    assert tl["name"] == "短剧1"
    assert tl["width"] == 1080


async def test_add_clips_and_transitions(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    # 创建时间线
    r = await client.post(
        "/api/v1/creative-studio/editor/timelines", json={}, headers=_h(token)
    )
    tl_id = r.json()["id"]

    # 添加视频片段
    r = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/clips",
        json={
            "track_type": "video", "source_url": "vid.mp4",
            "timeline_start": 0, "timeline_end": 4,
        },
        headers=_h(token),
    )
    assert r.status_code == 200
    clip_id = r.json()["clips"][-1]["id"]

    # 添加字幕
    r = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/clips",
        json={"track_type": "text", "text": "你好世界", "timeline_start": 1, "timeline_end": 3},
        headers=_h(token),
    )
    assert r.status_code == 200
    assert len(r.json()["clips"]) == 2

    # 添加转场
    r = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/transitions",
        json={"clip_id": clip_id, "type": "fade", "duration": 0.3},
        headers=_h(token),
    )
    assert r.status_code == 200
    assert len(r.json()["transitions"]) == 1


async def test_tenant_isolation(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["member"])
    r = await client.post(
        "/api/v1/creative-studio/editor/timelines", json={}, headers=_h(token_a)
    )
    tl_id = r.json()["id"]
    # 租户 B 看不到
    r = await client.get(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}", headers=_h(token_b)
    )
    assert r.status_code == 404


async def test_export_draft(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    r = await client.post(
        "/api/v1/creative-studio/editor/timelines", json={}, headers=_h(token)
    )
    tl_id = r.json()["id"]
    # 加片段
    await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/clips",
        json={"track_type": "video", "source_url": "v.mp4"},
        headers=_h(token),
    )
    # 导出草稿（未装 pyJianYingDraft -> 降级 JSON）
    r = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/export-draft",
        headers=_h(token),
    )
    assert r.status_code == 200
    assert r.json()["ok"]


async def test_render_without_moviepy(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    r = await client.post(
        "/api/v1/creative-studio/editor/timelines", json={}, headers=_h(token)
    )
    tl_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/creative-studio/editor/timelines/{tl_id}/render",
        json={}, headers=_h(token),
    )
    assert r.status_code == 200
    # 未装 MoviePy -> ok=False 但不崩
    body = r.json()
    assert "ok" in body


# ---- 智能体工具 ----


async def test_editor_tools_registered() -> None:
    from xagent.adapters.tools import get_tool_registry

    reg = get_tool_registry()
    names = reg.names()
    assert "editor_create_timeline" in names
    assert "editor_add_clip" in names
    assert "editor_render" in names
    assert "editor_export_draft" in names


async def test_editor_tool_create_and_add() -> None:
    from xagent.adapters.tools import get_tool_registry
    from xagent.adapters.tools.base import ToolContext
    from xagent.enterprise.auth.principal import Principal

    reg = get_tool_registry()
    ctx = ToolContext(principal=Principal(user_id="u", tenant_id="t1", roles=frozenset({"member"})))

    # 创建时间线
    r = await reg.call("editor_create_timeline", {"name": "工具测试"}, ctx)
    assert r.ok
    tl_id = r.output["timeline_id"]

    # 添加片段
    r = await reg.call("editor_add_clip", {
        "timeline_id": tl_id, "track_type": "video", "source_url": "v.mp4",
    }, ctx)
    assert r.ok
    assert len(r.output["timeline"]["clips"]) == 1
