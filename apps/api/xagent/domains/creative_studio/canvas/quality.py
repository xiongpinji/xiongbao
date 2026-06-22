"""画布节点级估算 / 评分 / 自动修复 —— 后端唯一权威实现。

前端右键菜单中的「资源估算 / 质量评估 / 自动修复」最终都路由到这里，
保证 lite / 网络模式下数据一致。
"""

from __future__ import annotations

import re
from typing import Any

from xagent.domains.creative_studio.canvas import (
    NodeStatus,
    NodeType,
    ProductionCanvas,
    ProductionNode,
)


def estimate_resource(node: ProductionNode) -> dict[str, Any]:
    """节点资源估算。返回 {vram_mb, time_seconds, difficulty}。"""
    settings = node.settings or {}
    if node.node_type is NodeType.keyframe:
        w, h = _parse_resolution(settings.get("resolution"), (1024, 1024))
        pixels = (w * h) / (1024 * 1024)
        steps = int(settings.get("steps") or 28)
        batch = int(settings.get("batch") or 1)
        vram = round(2200 + pixels * 1800 * batch)
        seconds = round(pixels * steps * batch * 0.35)
    elif node.node_type is NodeType.video:
        w, h = _parse_resolution(settings.get("resolution"), (1280, 720))
        pixels = (w * h) / (1024 * 1024)
        duration = float(settings.get("duration") or 5)
        steps = int(settings.get("steps") or 24)
        batch = int(settings.get("batch") or 1)
        vram = round(8000 + pixels * 3200 * batch)
        seconds = round(pixels * duration * steps * batch * 1.2)
    elif node.node_type is NodeType.voiceover:
        vram, seconds = 800, round(float(settings.get("duration") or 6) * 1.2)
    elif node.node_type is NodeType.soundtrack:
        vram, seconds = 1500, round(float(settings.get("duration") or 30) * 0.8)
    elif node.node_type is NodeType.subtitle:
        vram, seconds = 200, 5
    elif node.node_type is NodeType.storyboard:
        vram, seconds = 200, 8
    elif node.node_type in (NodeType.export,):
        vram, seconds = 600, 30
    else:
        vram, seconds = 100, 6

    return {
        "vram_mb": int(vram),
        "time_seconds": int(seconds),
        "difficulty": _difficulty(vram),
    }


def score_node(node: ProductionNode) -> dict[str, Any]:
    """六维节点质量评分（参考 X-Agent 视觉工作流的 quality_report）。"""
    settings = node.settings or {}
    prompt = str(settings.get("prompt") or node.content or "").strip()
    has_prompt = bool(prompt)
    has_deps = bool(node.dependencies) or node.node_type in (
        NodeType.brief_analysis,
        NodeType.plot_outline,
    )
    needs_sampling = node.node_type in (NodeType.keyframe, NodeType.video)
    param_complete = True
    if needs_sampling:
        param_complete = all(settings.get(key) for key in ("sampler", "steps", "cfg"))

    connectivity = 95 if has_deps else 65
    completeness = 92 if has_prompt else 50
    parameters = 90 if param_complete else 60
    security = 95
    executability = 40 if node.agent_note.startswith("执行失败") else 88
    resource_score = 70 if estimate_resource(node)["difficulty"] == "high" else 90
    overall = round(
        (connectivity + completeness + parameters + security + executability + resource_score) / 6
    )

    issues: list[str] = []
    if not has_prompt:
        issues.append("提示词为空")
    if needs_sampling and not param_complete:
        issues.append("采样参数不完整")
    if node.agent_note.startswith("执行失败"):
        issues.append("最近一次执行失败")

    return {
        "overall": overall,
        "connectivity": connectivity,
        "completeness": completeness,
        "parameters": parameters,
        "security": security,
        "executability": executability,
        "resource": resource_score,
        "issues": issues,
    }


def auto_fix(node: ProductionNode) -> dict[str, Any]:
    """根据节点类型补齐缺失参数；返回新的 settings patch（不会移除已有键）。"""
    settings = dict(node.settings or {})
    patch: dict[str, Any] = {}
    if node.node_type is NodeType.keyframe:
        defaults = {
            "sampler": "euler_a",
            "scheduler": "karras",
            "steps": 28,
            "cfg": 6.5,
            "resolution": "1024x1024",
            "batch": 1,
        }
    elif node.node_type is NodeType.video:
        defaults = {
            "sampler": "dpmpp_2m",
            "scheduler": "sgm_uniform",
            "steps": 24,
            "cfg": 6.0,
            "resolution": "1280x720",
            "duration": 5,
        }
    elif node.node_type is NodeType.voiceover:
        defaults = {"voice": "female_warm", "language": "zh-CN", "duration": 6}
    elif node.node_type is NodeType.soundtrack:
        defaults = {"bgm_style": "cinematic", "duration": 30}
    elif node.node_type is NodeType.storyboard:
        defaults = {"shot_type": "中景", "duration": 4}
    else:
        defaults = {}

    for key, value in defaults.items():
        if settings.get(key) in (None, "", 0):
            patch[key] = value

    if not settings.get("strategy"):
        patch["strategy"] = "balanced"
    if not settings.get("prompt"):
        prompt = str(node.content or "").strip() or node.title or node.node_type.value
        patch["prompt"] = prompt

    return patch


def estimate_canvas(canvas: ProductionCanvas) -> dict[str, Any]:
    per_node: list[dict[str, Any]] = []
    total_vram = 0
    total_time = 0
    for node in canvas.nodes:
        if node.locked:
            continue
        est = estimate_resource(node)
        per_node.append({"node_id": node.node_id, "node_type": node.node_type.value, **est})
        total_vram = max(total_vram, est["vram_mb"])  # 峰值显存
        total_time += est["time_seconds"]
    return {
        "nodes": per_node,
        "peak_vram_mb": total_vram,
        "total_time_seconds": total_time,
    }


def score_canvas(canvas: ProductionCanvas) -> dict[str, Any]:
    per_node: list[dict[str, Any]] = []
    overalls: list[int] = []
    for node in canvas.nodes:
        rep = score_node(node)
        per_node.append({"node_id": node.node_id, "node_type": node.node_type.value, **rep})
        overalls.append(rep["overall"])
    avg = round(sum(overalls) / len(overalls)) if overalls else 0
    return {
        "nodes": per_node,
        "overall": avg,
        "status_summary": _status_summary(canvas),
    }


def _status_summary(canvas: ProductionCanvas) -> dict[str, int]:
    summary = {status.value: 0 for status in NodeStatus}
    for node in canvas.nodes:
        summary[node.status.value] = summary.get(node.status.value, 0) + 1
    return summary


def _parse_resolution(value: Any, fallback: tuple[int, int]) -> tuple[int, int]:
    if not value:
        return fallback
    match = re.search(r"(\d+)\s*[x×*]\s*(\d+)", str(value), flags=re.IGNORECASE)
    if not match:
        return fallback
    return int(match.group(1)), int(match.group(2))


def _difficulty(vram_mb: float) -> str:
    if vram_mb >= 14000:
        return "high"
    if vram_mb >= 6000:
        return "medium"
    return "low"
