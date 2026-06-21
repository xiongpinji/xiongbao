"""质量门：故事板与成片的可验证检查。移植自旧仓 quality.py。

失败镜头可被定位并单独重试，与工作流引擎的补偿/回放语义衔接。
"""

from __future__ import annotations

from xagent.domains.creative_studio.storyboard import QualityGate, Storyboard

STORYBOARD_GATES = (
    "storyboard_fields",
    "shot_count",
    "duration",
    "subtitle_consistency",
)


def gate_storyboard_fields(sb: Storyboard) -> QualityGate:
    bad: list[str] = []
    for shot in sb.shots:
        if not shot.plot_purpose:
            bad.append(f"{shot.shot_id}:缺plot_purpose")
        if not shot.camera.shot_size:
            bad.append(f"{shot.shot_id}:缺景别")
        if not (shot.dialogue or shot.action):
            bad.append(f"{shot.shot_id}:缺台词/动作")
    return QualityGate(
        name="storyboard_fields",
        passed=not bad,
        detail="; ".join(bad) if bad else "所有镜头字段完整",
    )


def gate_shot_count(sb: Storyboard) -> QualityGate:
    n = len(sb.shots)
    ok = 3 <= n <= 12
    return QualityGate(
        name="shot_count",
        passed=ok,
        detail=f"镜头数 {n}" + ("" if ok else "（应在 3-12）"),
    )


def gate_duration(sb: Storyboard) -> QualityGate:
    total = sb.total_shot_duration()
    target = sb.target_duration_seconds or 1
    deviation = abs(total - target) / target
    ok = deviation <= 0.15
    return QualityGate(
        name="duration",
        passed=ok,
        detail=f"总时长 {total}s / 目标 {target}s，偏差 {deviation * 100:.0f}%",
    )


def gate_subtitle_consistency(sb: Storyboard) -> QualityGate:
    bad = [s.shot_id for s in sb.shots if s.dialogue and not s.subtitle]
    return QualityGate(
        name="subtitle_consistency",
        passed=not bad,
        detail="; ".join(bad) if bad else "字幕与台词一致",
    )


def run_gates(sb: Storyboard) -> list[QualityGate]:
    """运行全部质量门，返回结果列表。"""
    return [
        gate_storyboard_fields(sb),
        gate_shot_count(sb),
        gate_duration(sb),
        gate_subtitle_consistency(sb),
    ]
