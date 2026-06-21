"""短剧工厂 + 媒体 provider + 质量门测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.domains.creative_studio import build_draft_from_brief
from xagent.domains.creative_studio.media import (
    GenerationRequest,
    MediaKind,
    get_media_registry,
)
from xagent.domains.creative_studio.quality import run_gates
from xagent.domains.creative_studio.storyboard import (
    Shot,
    Storyboard,
)
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app


def test_draft_node_chain_has_review_gate() -> None:
    draft = build_draft_from_brief("霸总逆袭短剧", genre="逆袭", platform="抖音")
    assert draft.status == "pending_review"
    types = [n.node_type for n in draft.nodes]
    assert "人工审核导出" in types
    assert "关键帧" in types and "视频" in types
    # 末节点为审核门
    assert draft.nodes[-1].needs_review is True


async def test_null_media_provider_returns_placeholder() -> None:
    reg = get_media_registry()
    task = await reg.get(MediaKind.image).submit(
        GenerationRequest(kind=MediaKind.image, prompt="测试画面")
    )
    assert task.status == "succeeded"
    assert task.outputs


def test_quality_gates_pass_on_valid_storyboard() -> None:
    sb = Storyboard(
        title="t", brief="b", target_duration_seconds=12.0,
        shots=[
            Shot(duration_seconds=4, plot_purpose="引入", dialogue="你好", subtitle="你好"),
            Shot(duration_seconds=4, plot_purpose="冲突", dialogue="不行", subtitle="不行"),
            Shot(duration_seconds=4, plot_purpose="收尾", dialogue="再见", subtitle="再见"),
        ],
    )
    gates = run_gates(sb)
    assert all(g.passed for g in gates), [g.detail for g in gates]


def test_quality_gates_fail_on_missing_fields() -> None:
    sb = Storyboard(
        target_duration_seconds=12.0,
        shots=[Shot(), Shot()],  # 空 shot，缺字段且数量不足
    )
    gates = run_gates(sb)
    field_gate = next(g for g in gates if g.name == "storyboard_fields")
    assert not field_gate.passed
    count_gate = next(g for g in gates if g.name == "shot_count")
    assert not count_gate.passed


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_creative_draft_api(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post(
        "/api/v1/creative-studio/workflow-draft",
        json={"brief": "甜宠短剧", "genre": "甜宠", "platform": "快手"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["status"] == "pending_review"
    assert doc["tenant_id"] == "t1"
    draft_id = doc["draft_id"]

    # 审核通过
    r2 = await client.post(
        f"/api/v1/creative-studio/workflow-draft/{draft_id}/review",
        json={"approved": True, "comment": "ok"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "approved"


async def test_creative_tenant_isolation(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["member"])
    resp = await client.post(
        "/api/v1/creative-studio/workflow-draft",
        json={"brief": "x"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    draft_id = resp.json()["draft_id"]
    # 租户 B 审核租户 A 的草稿 -> 404
    r = await client.post(
        f"/api/v1/creative-studio/workflow-draft/{draft_id}/review",
        json={"approved": True},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
