"""短剧全链路编排测试：produce → 故事板+关键帧+视频+质量门。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.adapters.llm.base import LLMClient, LLMResponse, Message
from xagent.domains.creative_studio.pipeline import produce_short_drama
from xagent.enterprise.auth import create_access_token
from xagent.main import create_app


class _ScriptedLLM(LLMClient):
    """返回合法故事板 JSON 的测试 LLM。"""

    supports_tools = False

    async def complete(self, messages: list[Message], **kw) -> LLMResponse:  # noqa: ARG002
        import json

        payload = {
            "title": "霸总逆袭",
            "characters": [{"name": "苏总", "role": "霸总"}],
            "scenes": [{"location": "办公室", "description": "对峙"}],
            "shots": [
                {
                    "duration_seconds": 4, "scene": "办公室", "plot_purpose": "引入",
                    "dialogue": "你以为能赢？", "subtitle": "你以为能赢？",
                    "image_prompt": "冷峻霸总站在落地窗前",
                    "video_prompt": "镜头缓慢推近霸总侧脸",
                },
                {
                    "duration_seconds": 4, "scene": "办公室", "plot_purpose": "反转",
                    "dialogue": "我早赢了。", "subtitle": "我早赢了。",
                },
                {
                    "duration_seconds": 4, "scene": "走廊", "plot_purpose": "收尾",
                    "dialogue": "结束了。", "subtitle": "结束了。",
                },
            ],
        }
        return LLMResponse(content=json.dumps(payload, ensure_ascii=False), model="test")

    async def complete_with_tools(self, messages, tools, **kw):  # noqa: ARG002
        raise NotImplementedError

    async def health(self) -> bool:
        return True


@pytest.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_produce_full_pipeline() -> None:
    # Null media provider -> 占位产物；全链路应跑通
    result = await produce_short_drama("霸总逆袭", llm=_ScriptedLLM(), with_video=True)
    assert result.status == "produced"  # Null provider 不会失败
    assert len(result.shots) == 3
    # 每镜头有图 + 视频占位产物
    for shot in result.shots:
        assert shot.image_outputs
        assert shot.video_outputs
        assert shot.image_error is None
        assert shot.video_error is None
    # 第一个镜头用了自定义 image_prompt
    assert "霸总" in result.shots[0].image_prompt


async def test_produce_image_only() -> None:
    result = await produce_short_drama("甜宠", genre="甜宠", llm=_ScriptedLLM(), with_video=False)
    assert result.status == "produced"
    for shot in result.shots:
        assert shot.image_outputs
        assert shot.video_outputs == []  # 关闭视频


async def test_produce_api(client: AsyncClient) -> None:
    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    resp = await client.post(
        "/api/v1/creative-studio/produce",
        json={"brief": "逆袭短剧", "with_video": False},
        headers=_h(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("produced", "partial")
    assert body["shots"]
    assert body["tenant_id"] == "t1"
    sid = body["storyboard_id"]

    # 查产物列表
    r2 = await client.get("/api/v1/creative-studio/productions", headers=_h(token))
    assert r2.status_code == 200
    assert any(p["storyboard_id"] == sid for p in r2.json()["productions"])

    # 查产物详情
    r3 = await client.get(f"/api/v1/creative-studio/productions/{sid}", headers=_h(token))
    assert r3.status_code == 200
    assert r3.json()["storyboard_id"] == sid


async def test_produce_tenant_isolation(client: AsyncClient) -> None:
    token_a = create_access_token(user_id="a", tenant_id="tA", roles=["member"])
    token_b = create_access_token(user_id="b", tenant_id="tB", roles=["member"])
    resp = await client.post(
        "/api/v1/creative-studio/produce",
        json={"brief": "x", "with_video": False},
        headers=_h(token_a),
    )
    sid = resp.json()["storyboard_id"]
    # 租户 B 看不到 A 的产物
    r = await client.get(f"/api/v1/creative-studio/productions/{sid}", headers=_h(token_b))
    assert r.status_code == 404


async def test_produce_viewer_forbidden(client: AsyncClient) -> None:
    token = create_access_token(user_id="v", tenant_id="t1", roles=["viewer"])
    resp = await client.post(
        "/api/v1/creative-studio/produce",
        json={"brief": "x"},
        headers=_h(token),
    )
    assert resp.status_code == 403
