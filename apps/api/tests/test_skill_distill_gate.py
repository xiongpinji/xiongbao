"""技能自动提炼 + 质量门禁测试（对标 Hermes GEPA 闭环）。

覆盖：LLM 提炼 → 门禁（字段完整/触发可命中/去重）→ 入库或丢弃 全流程。
使用注入的假 LLM，离线可跑。
"""

from __future__ import annotations

import pytest

from xagent.adapters.llm.base import LLMResponse
from xagent.core.skills import SkillStore


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.fixture()
def store(tmp_path):
    """隔离的技能库（不污染全局 data/skills）。"""
    return SkillStore(storage_dir=tmp_path / "skills")


class FakeLLM:
    """可编程的假 LLM：返回预设内容或抛异常。"""

    supports_tools = False

    def __init__(self, content: str = "", exc: Exception | None = None):
        self._content = content
        self._exc = exc
        self.calls = 0

    async def complete(self, messages, **kwargs):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return LLMResponse(content=self._content, model="fake")


_GOAL = "为短剧项目创建分镜脚本并生成关键帧图片"
_ANSWER = "已完成分镜脚本创建并生成 4 张关键帧图片，每一步均验证通过。" * 4
_TOOLS = ["filesystem", "media_generate", "editor"]

_GOOD_JSON = (
    '{"name": "短剧分镜关键帧生成", '
    '"description": "为短剧项目创建分镜脚本并批量生成关键帧图片", '
    '"trigger": "短剧|分镜|关键帧", '
    '"hint": "先写分镜脚本落盘，再逐镜头调用 media_generate 生成关键帧"}'
)


class TestAutoDistillFlow:
    @pytest.mark.anyio
    async def test_distill_gate_pass_and_store(self, store):
        """LLM 提炼 → 门禁通过 → 入库，source=auto_distilled。"""
        llm = FakeLLM(content=f"提炼结果：\n{_GOOD_JSON}")
        skill = await store.auto_distill(
            goal=_GOAL, answer=_ANSWER, steps_count=6, tools_used=_TOOLS, llm=llm,
        )
        assert llm.calls == 1
        assert skill is not None
        assert skill.source == "auto_distilled"
        assert skill.name == "短剧分镜关键帧生成"
        assert "auto_distilled" in skill.tags
        assert [s["tool"] for s in skill.steps] == _TOOLS
        # 触发模式可被匹配器命中
        assert store.match(_GOAL)[0].skill_id == skill.skill_id
        # 统计口径
        assert store.stats()["auto_distilled"] == 1

    @pytest.mark.anyio
    async def test_llm_failure_silent_skip(self, store):
        """LLM 调用失败 → 静默跳过，不入库。"""
        llm = FakeLLM(exc=RuntimeError("provider down"))
        skill = await store.auto_distill(
            goal=_GOAL, answer=_ANSWER, steps_count=6, tools_used=_TOOLS, llm=llm,
        )
        assert skill is None
        assert store.list_all() == []

    @pytest.mark.anyio
    async def test_llm_invalid_json_silent_skip(self, store):
        """LLM 输出非 JSON → 静默跳过。"""
        llm = FakeLLM(content="我无法提炼这个任务")
        skill = await store.auto_distill(
            goal=_GOAL, answer=_ANSWER, steps_count=6, tools_used=_TOOLS, llm=llm,
        )
        assert skill is None
        assert store.list_all() == []

    @pytest.mark.anyio
    async def test_mock_llm_client_silent_skip(self, store):
        """无真实 LLM（Mock 降级客户端）→ 静默跳过，不调用 complete。"""
        from xagent.adapters.llm.mock import MockLLMClient

        skill = await store.auto_distill(
            goal=_GOAL, answer=_ANSWER, steps_count=6, tools_used=_TOOLS,
            llm=MockLLMClient(),
        )
        assert skill is None
        assert store.list_all() == []

    @pytest.mark.anyio
    async def test_preconditions_skip(self, store):
        """步数不足 / 内容不足 → 不调用 LLM 直接跳过。"""
        llm = FakeLLM(content=_GOOD_JSON)
        assert await store.auto_distill(goal=_GOAL, answer=_ANSWER, steps_count=1, llm=llm) is None
        assert await store.auto_distill(goal=_GOAL, answer="ok", steps_count=6, tools_used=["a"], llm=llm) is None
        assert llm.calls == 0


class TestGate:
    @pytest.mark.anyio
    async def test_gate_reject_incomplete_fields(self, store):
        """字段不完整 → 门禁拒绝。"""
        bad = '{"name": "x", "description": "", "trigger": "短剧", "hint": "y"}'
        skill = await store.auto_distill(
            goal=_GOAL, answer=_ANSWER, steps_count=6, tools_used=_TOOLS,
            llm=FakeLLM(content=bad),
        )
        assert skill is None
        assert store.list_all() == []

    @pytest.mark.anyio
    async def test_gate_reject_trigger_not_matchable(self, store):
        """触发关键词与任务目标无关（匹配器无法命中）→ 门禁拒绝。"""
        bad = (
            '{"name": "数据库迁移", "description": "数据库 schema 迁移流程", '
            '"trigger": "数据库|迁移|schema", "hint": "先备份再迁移"}'
        )
        skill = await store.auto_distill(
            goal=_GOAL, answer=_ANSWER, steps_count=6, tools_used=_TOOLS,
            llm=FakeLLM(content=bad),
        )
        assert skill is None
        assert store.list_all() == []

    @pytest.mark.anyio
    async def test_gate_reject_duplicate(self, store):
        """与现有技能相似度超阈值 → 门禁拒绝去重。"""
        llm = FakeLLM(content=_GOOD_JSON)
        first = await store.auto_distill(
            goal=_GOAL, answer=_ANSWER, steps_count=6, tools_used=_TOOLS, llm=llm,
        )
        assert first is not None
        # 再次提炼高度相似的候选 → 拒绝
        dup = await store.auto_distill(
            goal=_GOAL, answer=_ANSWER, steps_count=7, tools_used=_TOOLS, llm=llm,
        )
        assert dup is None
        assert len(store.list_all()) == 1

    def test_gate_unit(self, store):
        """门禁函数单测：各拒绝原因。"""
        good = {
            "name": "n", "description": "d", "trigger_pattern": "短剧|分镜",
            "system_prompt_hint": "h",
        }
        ok, reason = store.gate_candidate(good, _GOAL)
        assert ok and reason == ""

        ok, reason = store.gate_candidate({**good, "name": ""}, _GOAL)
        assert not ok and reason.startswith("incomplete_field")

        ok, reason = store.gate_candidate({**good, "trigger_pattern": "zz|qq"}, _GOAL)
        assert not ok and reason == "trigger_not_matchable"


class TestDistilledLifecycle:
    @pytest.mark.anyio
    async def test_auto_distilled_keeps_manual_lifecycle(self, store):
        """自动提炼的技能保留人工 evolve/retire/restore 生命周期。"""
        skill = await store.auto_distill(
            goal=_GOAL, answer=_ANSWER, steps_count=6, tools_used=_TOOLS,
            llm=FakeLLM(content=_GOOD_JSON),
        )
        assert skill is not None
        # evolve
        evolved = store.evolve_skill(skill.skill_id, description="v2 描述", change_reason="人工优化")
        assert evolved is not None and evolved.version == 2
        assert len(evolved.history) == 1
        # retire via 低成功率
        for _ in range(5):
            store.record_usage(skill.skill_id, success=False)
        assert store.get(skill.skill_id).retired is True
        # restore
        assert store.restore_skill(skill.skill_id) is True
        assert store.get(skill.skill_id).retired is False
