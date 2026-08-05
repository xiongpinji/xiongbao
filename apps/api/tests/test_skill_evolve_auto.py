"""技能自动进化闭环测试（GEPA 轻量落地：变体生成 → 评测打分 → 优胜入库）。

覆盖：
- 全流程采纳：变体显著优于父代 → 走 evolve 版本化替换，history 记录原因与得分
- 拒绝：变体不显著优于父代 → 丢弃，技能不变
- 无 LLM 降级：Mock 客户端 → 跳过；评测任务生成失败 → 纯匹配器准确率
- 阈值边界：分差 == 阈值采纳，略低于阈值拒绝
- POST /api/v1/skills/{id}/evolve-auto 端点（无 LLM 降级 + 404）
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.adapters.llm.base import LLMResponse
from xagent.core.skills import SkillStore


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.fixture()
def store(tmp_path):
    return SkillStore(storage_dir=tmp_path / "skills")


class RoutedFakeLLM:
    """按 prompt 内容路由的假 LLM：评测样例 / 变体生成分别返回预设内容。"""

    supports_tools = False

    def __init__(self, eval_content: str = "", variant_content: str = "",
                 variant_exc: Exception | None = None):
        self._eval = eval_content
        self._variant = variant_content
        self._variant_exc = variant_exc
        self.calls = 0

    async def complete(self, messages, **kwargs):
        self.calls += 1
        prompt = messages[-1].content
        if "评测样例" in prompt:
            return LLMResponse(content=self._eval, model="fake")
        if self._variant_exc is not None:
            raise self._variant_exc
        return LLMResponse(content=self._variant, model="fake")


def _make_parent(store: SkillStore):
    return store.create_skill(
        name="短剧分镜生成",
        description="为短剧创建分镜脚本并生成关键帧",
        trigger_pattern="分镜",
        system_prompt_hint="先写分镜脚本落盘",
        steps=[{"tool": "filesystem", "order": 0}],
        source="manual",
        source_task="为短剧创建分镜脚本",
    )


# 父代 trigger=「分镜」只能命中 2/4 正例；变体补充关键词后 4/4 全命中
_EVAL_JSON = (
    '{"positive": ["写短剧分镜", "做故事板设计", "分镜脚本优化", "帮我画storyboard"], '
    '"negative": ["数据库备份方案", "服务器部署流程", "写一封求职信"]}'
)

_GOOD_VARIANTS = (
    '[{"description": "为短剧创建分镜/故事板并生成关键帧图片", '
    '"trigger_pattern": "分镜|故事板|storyboard", '
    '"system_prompt_hint": "先写分镜脚本落盘，再逐镜头生成关键帧", '
    '"steps": [{"tool": "filesystem", "order": 0}, {"tool": "media_generate", "order": 1}]},'
    '{"description": "短剧视觉预演流程", "trigger_pattern": "分镜|预演", '
    '"system_prompt_hint": "先分镜后预演", "steps": [{"tool": "filesystem", "order": 0}]}]'
)

# 与父代等价的变体（不显著优于父代）
_SAME_VARIANTS = (
    '[{"description": "为短剧创建分镜脚本", "trigger_pattern": "分镜", '
    '"system_prompt_hint": "先写分镜脚本落盘", "steps": [{"tool": "filesystem", "order": 0}]}]'
)


class TestEvolveAutoFlow:
    @pytest.mark.anyio
    async def test_adopt_better_variant(self, store):
        """变体显著优于父代 → 采纳，版本化 + history 记录原因与得分。"""
        skill = _make_parent(store)
        llm = RoutedFakeLLM(eval_content=_EVAL_JSON, variant_content=_GOOD_VARIANTS)
        result = await store.evolve_auto(skill.skill_id, llm=llm)

        assert result["adopted"] is True
        assert result["parent_score"] is not None
        assert len(result["variants"]) == 2
        assert result["best_score"] >= result["parent_score"] + 0.1
        assert "auto_evolve" in result["reason"]
        # 变体与父代均被评测打分
        for v in result["variants"]:
            assert 0.0 <= v["score"] <= 1.0

        evolved = store.get(skill.skill_id)
        assert evolved.version == 2
        assert evolved.source == "evolved"
        assert evolved.trigger_pattern == "分镜|故事板|storyboard"
        # history 记录进化原因与得分
        assert len(evolved.history) == 1
        assert "auto_evolve" in evolved.history[0]["change_reason"]
        assert str(result["parent_score"])[:3] in evolved.history[0]["change_reason"]

    @pytest.mark.anyio
    async def test_reject_non_improving_variant(self, store):
        """变体不显著优于父代 → 拒绝，技能保持不变。"""
        skill = _make_parent(store)
        llm = RoutedFakeLLM(eval_content=_EVAL_JSON, variant_content=_SAME_VARIANTS)
        result = await store.evolve_auto(skill.skill_id, llm=llm)

        assert result["adopted"] is False
        assert result["reason"].startswith("below_threshold")
        unchanged = store.get(skill.skill_id)
        assert unchanged.version == 1
        assert unchanged.trigger_pattern == "分镜"
        assert unchanged.history == []

    @pytest.mark.anyio
    async def test_threshold_boundary(self, store):
        """分差 == 阈值 → 采纳；阈值略大于分差 → 拒绝。"""
        skill = _make_parent(store)
        llm = RoutedFakeLLM(eval_content=_EVAL_JSON, variant_content=_GOOD_VARIANTS)
        first = await store.evolve_auto(skill.skill_id, llm=llm)
        diff = round(first["best_score"] - first["parent_score"], 4)
        assert diff > 0

        # 分差恰好等于阈值 → 采纳
        store2 = SkillStore(storage_dir=store._dir.parent / "s2")
        s2 = _make_parent(store2)
        r2 = await store2.evolve_auto(
            s2.skill_id, threshold=diff,
            llm=RoutedFakeLLM(eval_content=_EVAL_JSON, variant_content=_GOOD_VARIANTS),
        )
        assert r2["adopted"] is True

        # 阈值略大于分差 → 拒绝
        store3 = SkillStore(storage_dir=store._dir.parent / "s3")
        s3 = _make_parent(store3)
        r3 = await store3.evolve_auto(
            s3.skill_id, threshold=diff + 0.001,
            llm=RoutedFakeLLM(eval_content=_EVAL_JSON, variant_content=_GOOD_VARIANTS),
        )
        assert r3["adopted"] is False
        assert store3.get(s3.skill_id).version == 1

    @pytest.mark.anyio
    async def test_skill_not_found(self, store):
        result = await store.evolve_auto("no-such", llm=RoutedFakeLLM())
        assert result is None


class TestDegradation:
    @pytest.mark.anyio
    async def test_no_llm_skip(self, store):
        """无真实 LLM（Mock 降级客户端）→ 跳过闭环，不改动技能。"""
        from xagent.adapters.llm.mock import MockLLMClient

        skill = _make_parent(store)
        result = await store.evolve_auto(skill.skill_id, llm=MockLLMClient())
        assert result["adopted"] is False
        assert result["reason"] == "no_llm"
        assert result["parent_score"] is None
        assert store.get(skill.skill_id).version == 1

    @pytest.mark.anyio
    async def test_variant_llm_failure(self, store):
        """变体生成 LLM 失败 → no_variants，父代已被打分但技能不变。"""
        skill = _make_parent(store)
        llm = RoutedFakeLLM(eval_content=_EVAL_JSON, variant_exc=RuntimeError("down"))
        result = await store.evolve_auto(skill.skill_id, llm=llm)
        assert result["adopted"] is False
        assert result["reason"] == "no_variants"
        assert result["parent_score"] is not None
        assert store.get(skill.skill_id).version == 1

    @pytest.mark.anyio
    async def test_eval_tasks_failure_fallback_matcher(self, store):
        """评测任务生成失败 → 降级纯匹配器准确率，闭环仍可运行。"""
        skill = _make_parent(store)
        llm = RoutedFakeLLM(eval_content="无法生成", variant_content=_SAME_VARIANTS)
        result = await store.evolve_auto(skill.skill_id, llm=llm)
        assert result["parent_eval"]["eval_mode"] == "matcher_only"
        # 父代触发模式可命中自身语境 → 匹配准确率 1.0
        assert result["parent_eval"]["match_accuracy"] == 1.0
        # 等价变体无提升 → 拒绝
        assert result["adopted"] is False

    @pytest.mark.anyio
    async def test_generate_variants_no_llm_returns_empty(self, store):
        """变体生成：无 LLM 直接返回空列表。"""
        from xagent.adapters.llm.mock import MockLLMClient

        skill = _make_parent(store)
        assert await store.generate_variants(skill, llm=MockLLMClient()) == []


class TestEvaluator:
    def test_evaluate_fields_synthetic(self, store):
        """合成评测：匹配准确率 = 正确数/总数；完整度独立计分。"""
        fields = {
            "name": "n", "description": "d", "trigger_pattern": "分镜",
            "system_prompt_hint": "h", "steps": [{"tool": "t"}],
        }
        ev = store.evaluate_fields(
            fields,
            eval_tasks={"positive": ["写分镜", "别的任务"], "negative": ["无关事情"]},
        )
        # 正例 1/2 命中 + 负例 1/1 未命中 = 2/3
        assert abs(ev["match_accuracy"] - 2 / 3) < 1e-4
        assert ev["completeness"] == 1.0
        assert ev["eval_mode"] == "synthetic"
        assert abs(ev["score"] - (0.6 * 2 / 3 + 0.2 * 1.0 + 0.2 * 0.5)) < 1e-3

    def test_evaluate_fields_incomplete(self, store):
        """字段缺失降低完整度分。"""
        fields = {"name": "", "description": "d", "trigger_pattern": "分镜",
                  "system_prompt_hint": "", "steps": []}
        ev = store.evaluate_fields(fields)
        assert ev["completeness"] == pytest.approx(0.4)

    def test_evaluate_fields_history(self, store):
        """有使用记录时历史分量取真实成功率。"""
        fields = {"name": "n", "description": "d", "trigger_pattern": "分镜",
                  "system_prompt_hint": "h", "steps": []}
        ev = store.evaluate_fields(fields, success_rate=0.8, has_history=True)
        assert ev["history"] == 0.8


# ─── API 端点 ───


@pytest.fixture()
async def client():
    from xagent.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _h() -> dict:
    from xagent.enterprise.auth import create_access_token

    token = create_access_token(user_id="u", tenant_id="t1", roles=["member"])
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_evolve_auto_endpoint_not_found(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/skills/no-such-skill/evolve-auto", headers=_h())
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_evolve_auto_endpoint_no_llm_degrades(client: AsyncClient) -> None:
    """测试环境无真实 LLM → 端点诚实返回 no_llm 降级，不伪造进化结果。"""
    from xagent.core.skills import get_skill_store

    store = get_skill_store()
    skill = store.create_skill(
        name="evolve-auto-api-test", description="端点降级测试技能",
        trigger_pattern="evolveautokw", system_prompt_hint="h",
    )
    try:
        resp = await client.post(
            f"/api/v1/skills/{skill.skill_id}/evolve-auto", headers=_h(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["adopted"] is False
        assert data["reason"] == "no_llm"
        assert data["parent_score"] is None
        # 未改动技能
        assert store.get(skill.skill_id).version == 1
    finally:
        store.delete(skill.skill_id)
