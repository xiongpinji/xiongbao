"""技能系统反噬防护回归（2026-09-06 实测发现，v1.3.1）。

事故：auto_distill 产出 trigger=创建|打印|读取|确认 的技能 →
匹配一切创建类任务 → 小模型把技能定义 JSON 原样复述给用户。
"""

from __future__ import annotations

import pytest
from xagent.core.orchestration.loop import _is_skill_definition_echo
from xagent.core.skills import SkillStore


@pytest.fixture
def store(tmp_path):
    return SkillStore(tmp_path / "skills")


def _candidate(**over):
    base = {
        "name": "VerifyAgentFile",
        "description": "创建并验证Python文件",
        "trigger_pattern": "创建|打印|读取|确认",
        "system_prompt_hint": "使用 file_write 写入后 file_read 确认",
        "steps": [{"tool": "file_write", "order": 0}],
        "source_task": "创建 agent_v130_check.py 打印 Agent Mode Works 然后读取确认",
    }
    base.update(over)
    return base


# ─── 1. 门禁：全泛词触发模式拒绝 ───


def test_gate_rejects_all_generic_trigger(store):
    ok, reason = store.gate_candidate(_candidate(), goal=_candidate()["source_task"])
    assert not ok
    assert reason == "trigger_too_generic"


def test_gate_accepts_specific_trigger(store):
    ok, reason = store.gate_candidate(
        _candidate(trigger_pattern="计算器|calculator"),
        goal="写一个计算器并运行",
    )
    assert ok, reason


def test_gate_accepts_mixed_with_at_least_one_specific(store):
    ok, reason = store.gate_candidate(
        _candidate(trigger_pattern="创建|斐波那契"),
        goal="创建斐波那契脚本",
    )
    assert ok, reason


def test_gate_rejects_english_generic_only(store):
    ok, reason = store.gate_candidate(
        _candidate(trigger_pattern="create|write|file"),
        goal="create and write the file",
    )
    assert not ok
    assert reason == "trigger_too_generic"


# ─── 2. 注入措辞：明确禁止复述 ───


def test_injection_forbids_echo(store):
    store.create_skill(
        name="CalcSkill",
        description="计算器做法",
        trigger_pattern="计算器",
        system_prompt_hint="用 ast 解析",
    )
    injection = store.build_prompt_injection("写一个计算器")
    assert "计算器" in injection
    assert "禁止" in injection and "原样输出" in injection


def test_no_match_no_injection(store):
    assert store.build_prompt_injection("完全不相关的目标") == ""


# ─── 3. 复读检测器 ───


def test_skill_echo_detector_positive():
    text = (
        '{"name": "AgentFileCheck", "description": "创建文件", '
        '"trigger": "创建|打印", "hint": "写文件"}'
    )
    assert _is_skill_definition_echo(text) is True


def test_skill_echo_detector_json_fence():
    text = '```json\n{"name": "X", "trigger": "a|b", "hint": "y"}\n```'
    assert _is_skill_definition_echo(text) is True


def test_skill_echo_detector_negative_normal_answer():
    assert _is_skill_definition_echo("计算器已创建，支持加减乘除。") is False


def test_skill_echo_detector_negative_tool_payload():
    # 工具返回 JSON（如文件列表）不应误判：无 trigger/name+hint 组合
    assert _is_skill_definition_echo('{"total_count": 3, "files": []}') is False


def test_skill_echo_detector_negative_real_code():
    code = '{ "fib": [0, 1], "n": 10 }'
    assert _is_skill_definition_echo(code) is False


# ─── 4. 蒸馏技能默认不启用（人工启用才注入）───


def test_distilled_skill_created_disabled(store):
    """auto/failure 蒸馏入库即 enabled=False——不参与匹配注入。"""
    # 直接用 create 路径（绕过 LLM）：验证 create_skill 显式传参
    s_auto = store.create_skill(
        name="AutoSkill", description="d", trigger_pattern="特定词xyz",
        system_prompt_hint="h", source="auto_distilled", enabled=False,
    )
    assert s_auto.enabled is False
    assert store.match("包含 特定词xyz 的目标") == []


def test_enabled_gate_controls_injection(store):
    s = store.create_skill(
        name="TipSkill", description="d", trigger_pattern="计算器",
        system_prompt_hint="用 ast", enabled=False,
    )
    assert store.build_prompt_injection("写一个计算器") == ""
    ok = store.set_enabled(s.skill_id, True)
    assert ok is True
    assert "TipSkill" in store.build_prompt_injection("写一个计算器")
    ok2 = store.set_enabled(s.skill_id, False)
    assert ok2 is True
    assert store.build_prompt_injection("写一个计算器") == ""


def test_manual_skill_still_enabled_by_default(store):
    s = store.create_skill(name="ManualSkill", description="d", trigger_pattern="手工词")
    assert s.enabled is True
    assert len(store.match("带 手工词 的目标")) == 1


def test_legacy_json_without_enabled_field_defaults_active(tmp_path):
    """旧技能 JSON 无 enabled 字段 → 默认启用（向后兼容存量技能）。"""
    import json as _json
    d = tmp_path / "skills"
    d.mkdir()
    (d / "legacy01.json").write_text(_json.dumps({
        "skill_id": "legacy01", "name": "Legacy", "description": "d",
        "trigger_pattern": "遗留词", "steps": [], "system_prompt_hint": "h",
    }), encoding="utf-8")
    store = SkillStore(d)
    matches = store.match("含 遗留词 的目标")
    assert len(matches) == 1 and matches[0].enabled is True
