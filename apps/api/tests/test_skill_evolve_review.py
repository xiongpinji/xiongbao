"""V3-2 技能进化闭环硬化测试：人工审核流 + 变体留证 + 失败反思提炼。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from xagent.adapters.llm.base import LLMResponse
from xagent.core.skills import SkillStore


@pytest.fixture()
def store(tmp_path):
    return SkillStore(storage_dir=tmp_path / "skills")


class RoutedFakeLLM:
    """按 prompt 内容路由的假 LLM（沿用 test_skill_evolve_auto 模式）。"""

    supports_tools = False

    def __init__(self, eval_content: str = "", variant_content: str = "",
                 failure_content: str = ""):
        self._eval = eval_content
        self._variant = variant_content
        self._failure = failure_content

    async def complete(self, messages, **kwargs):
        prompt = messages[-1].content
        if "评测样例" in prompt:
            return LLMResponse(content=self._eval, model="fake")
        if "失败分析专家" in prompt:
            return LLMResponse(content=self._failure, model="fake")
        return LLMResponse(content=self._variant, model="fake")


EVAL_JSON = (
    '{"positive": ["写短剧分镜", "做故事板设计", "分镜脚本优化", "帮我画storyboard"], '
    '"negative": ["数据库备份方案", "服务器部署流程", "写一封求职信"]}'
)
# 父代 trigger=「分镜」只命中 2/4 正例；变体补充关键词后 4/4 全命中 → 显著优胜
VARIANT_JSON = (
    '[{"description": "为短剧创建分镜/故事板并生成关键帧图片", '
    '"trigger_pattern": "分镜|故事板|storyboard", '
    '"system_prompt_hint": "先写分镜脚本落盘，再逐镜头生成关键帧", '
    '"steps": [{"tool": "filesystem", "order": 0}, {"tool": "media_generate", "order": 1}]}]'
)
FAILURE_JSON = (
    '{"name": "避免LLM超时", "description": "调用LLM执行任务时避免超时失败", '
    '"trigger_pattern": "LLM|任务", '
    '"system_prompt_hint": "先缩小上下文再调用，超时切换 fallback 模型", "steps": []}'
)


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


# ─── 人工审核流 ───


async def test_evolve_auto_require_review_pends_instead_of_adopting(
    store: SkillStore,
) -> None:
    parent = _make_parent(store)
    llm = RoutedFakeLLM(eval_content=EVAL_JSON, variant_content=VARIANT_JSON)
    result = await store.evolve_auto(
        parent.skill_id, llm=llm, threshold=0.05, require_review=True,
    )
    assert result["adopted"] is False
    assert result["reason"].startswith("pending_review:")
    pending_id = result["pending_id"]
    # 技能未被改动
    assert store.get(parent.skill_id).version == 1
    # 挂起条目可见
    pending = store.list_pending_evolutions()
    assert [p["pending_id"] for p in pending] == [pending_id]
    assert pending[0]["best_eval"]["score"] >= pending[0]["parent_eval"]["score"]


async def test_approve_evolution_applies_variant(store: SkillStore) -> None:
    parent = _make_parent(store)
    llm = RoutedFakeLLM(eval_content=EVAL_JSON, variant_content=VARIANT_JSON)
    result = await store.evolve_auto(
        parent.skill_id, llm=llm, threshold=0.05, require_review=True,
    )
    approved = store.approve_evolution(result["pending_id"])
    assert approved is not None and approved["approved"] is True
    evolved = store.get(parent.skill_id)
    assert evolved.version == 2
    assert "故事板" in evolved.description
    assert evolved.history[-1]["change_reason"].startswith("approved:")
    # 队列已清空；重复批准返回 None
    assert store.list_pending_evolutions() == []
    assert store.approve_evolution(result["pending_id"]) is None


async def test_reject_evolution_discards_variant(store: SkillStore) -> None:
    parent = _make_parent(store)
    llm = RoutedFakeLLM(eval_content=EVAL_JSON, variant_content=VARIANT_JSON)
    result = await store.evolve_auto(
        parent.skill_id, llm=llm, threshold=0.05, require_review=True,
    )
    assert store.reject_evolution(result["pending_id"]) is True
    assert store.get(parent.skill_id).version == 1
    assert store.reject_evolution(result["pending_id"]) is False


async def test_pending_survives_store_reload(store: SkillStore, tmp_path) -> None:
    """挂起队列落盘持久化：新 SkillStore 实例（模拟重启）仍可见。"""
    parent = _make_parent(store)
    llm = RoutedFakeLLM(eval_content=EVAL_JSON, variant_content=VARIANT_JSON)
    result = await store.evolve_auto(
        parent.skill_id, llm=llm, threshold=0.05, require_review=True,
    )
    store2 = SkillStore(storage_dir=tmp_path / "skills")
    pending = store2.list_pending_evolutions()
    assert [p["pending_id"] for p in pending] == [result["pending_id"]]
    approved = store2.approve_evolution(result["pending_id"])
    assert approved is not None
    assert store2.get(parent.skill_id).version == 2


async def test_default_mode_still_auto_adopts(store: SkillStore) -> None:
    """不传 require_review 时保持原自动采纳行为（向后兼容）。"""
    parent = _make_parent(store)
    llm = RoutedFakeLLM(eval_content=EVAL_JSON, variant_content=VARIANT_JSON)
    result = await store.evolve_auto(parent.skill_id, llm=llm, threshold=0.05)
    assert result["adopted"] is True
    assert store.get(parent.skill_id).version == 2
    assert store.list_pending_evolutions() == []


# ─── 失败反思提炼 ───


async def test_distill_from_failure_creates_skill(store: SkillStore) -> None:
    llm = RoutedFakeLLM(failure_content=FAILURE_JSON)
    skill = await store.distill_from_failure(
        "调用 LLM 执行长上下文任务", "LLM request timeout after 60s",
        tools_used=["llm"], llm=llm,
    )
    assert skill is not None
    assert skill.source == "failure_distilled"
    assert "超时" in skill.name or "超时" in skill.description
    assert "failure_distilled" in skill.tags
    assert skill.source_task.startswith("failure:")


async def test_distill_from_failure_no_llm_degrades(store: SkillStore) -> None:
    assert await store.distill_from_failure("g", "err", llm=None) is None


async def test_distill_from_failure_gate_rejects_garbage(store: SkillStore) -> None:
    llm = RoutedFakeLLM(failure_content='{"name": "", "description": ""}')
    assert await store.distill_from_failure("任务目标", "err", llm=llm) is None
    assert store.stats()["total"] == 0


# ─── API 层：审核队列端点 + 变体留证 ───


@pytest.fixture
async def client():
    from xagent.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_pending_endpoints_empty_and_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    lst = await client.get("/api/v1/skills/evolutions/pending", headers=headers)
    assert lst.status_code == 200
    assert lst.json()["total"] == 0
    missing = await client.post(
        "/api/v1/skills/evolutions/nope/approve", headers=headers
    )
    assert missing.status_code == 404
    missing2 = await client.post(
        "/api/v1/skills/evolutions/nope/reject", headers=headers
    )
    assert missing2.status_code == 404
