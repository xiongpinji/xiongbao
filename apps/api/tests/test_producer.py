"""短剧制作人 LLM 编排测试。"""

from __future__ import annotations

from xagent.adapters.llm.base import LLMClient, LLMResponse, Message
from xagent.adapters.llm.mock import MockLLMClient
from xagent.domains.creative_studio.producer import generate_storyboard
from xagent.domains.creative_studio.quality import run_gates
from xagent.domains.creative_studio.storyboard import StoryboardStatus


class _ScriptedLLM(LLMClient):
    """返回合法故事板 JSON 的测试 LLM。"""

    supports_tools = False

    async def complete(self, messages: list[Message], **kw) -> LLMResponse:  # noqa: ARG002
        import json

        payload = {
            "title": "霸总逆袭",
            "characters": [
                {"name": "苏总", "role": "霸总", "appearance": "西装", "personality": "冷峻"}
            ],
            "scenes": [{"location": "办公室", "time_of_day": "day", "description": "对峙"}],
            "shots": [
                {
                    "duration_seconds": 4, "scene": "办公室", "characters": ["苏总"],
                    "plot_purpose": "引入", "camera": {"shot_size": "medium", "movement": "static"},
                    "lighting": {"style": "冷光", "mood": "紧张"},
                    "dialogue": "你以为能赢？", "subtitle": "你以为能赢？",
                },
                {
                    "duration_seconds": 4, "scene": "办公室", "characters": ["苏总"],
                    "plot_purpose": "反转", "camera": {"shot_size": "close", "movement": "push"},
                    "lighting": {"style": "冷光", "mood": "紧张"},
                    "dialogue": "我早赢了。", "subtitle": "我早赢了。",
                },
            ],
        }
        return LLMResponse(content=json.dumps(payload, ensure_ascii=False), model="test")

    async def complete_with_tools(self, messages, tools, **kw):  # noqa: ARG002
        raise NotImplementedError

    async def health(self) -> bool:
        return True


async def test_storyboard_from_llm() -> None:
    sb = await generate_storyboard("霸总逆袭", llm=_ScriptedLLM())
    assert sb.status == StoryboardStatus.SCRIPTED
    assert len(sb.shots) == 2
    assert sb.characters[0].name == "苏总"
    # 质量门：2 镜头会触发 shot_count 门失败，但字段门应过
    gates = run_gates(sb)
    field_gate = next(g for g in gates if g.name == "storyboard_fields")
    assert field_gate.passed


async def test_storyboard_fallback_on_mock() -> None:
    # MockLLM 返回非 JSON -> 走保底模板
    sb = await generate_storyboard(
        "甜宠", genre="甜宠", llm=MockLLMClient(), target_duration_seconds=40
    )
    assert sb.status == StoryboardStatus.DRAFT
    assert sb.shots  # 保底有镜头
    assert sb.characters[0].role == "甜宠"


async def test_storyboard_fallback_on_exception() -> None:
    class _Boom(LLMClient):
        supports_tools = False

        async def complete(self, *a, **k):  # noqa: ARG002
            raise RuntimeError("boom")

        async def complete_with_tools(self, *a, **k):  # noqa: ARG002
            raise RuntimeError("boom")

        async def health(self) -> bool:
            return False

    sb = await generate_storyboard("重生", llm=_Boom())
    assert sb.status == StoryboardStatus.DRAFT
    assert sb.shots
