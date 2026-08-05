"""短剧生产节点链：无限节点 DAG，智能体生成，人工可审核编辑每个节点。

节点类型链（智能体自动生成）：
  需求分析 → 梗概 → 角色设定 → 分镜 → 关键帧(image)
  → 视频 → 配音 → 字幕 → 配乐 → 导出

每节点支持：status（pending/approved/rejected/modified）、
agent_note（智能体说明）、human_note（人工修改意见/指令）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class NodeType(str, Enum):
    brief_analysis = "需求分析"
    plot_outline = "梗概"
    character_setting = "角色设定"
    storyboard = "分镜"
    keyframe = "关键帧"
    video = "视频"
    voiceover = "配音"
    subtitle = "字幕"
    soundtrack = "配乐"
    export = "导出"


class NodeStatus(str, Enum):
    pending = "pending"
    review_required = "review_required"
    approved = "approved"
    rejected = "rejected"
    modified = "modified"


@dataclass
class ProductionNode:
    node_id: str = field(default_factory=lambda: uuid4().hex[:8])
    node_type: NodeType = NodeType.brief_analysis
    title: str = ""
    content: Any = None          # 智能体产出的内容（文本/图文/视频URL等）
    status: NodeStatus = NodeStatus.pending
    agent_note: str = ""         # 智能体说明
    human_note: str = ""         # 人工修改意见
    position: dict = field(default_factory=lambda: {"x": 0, "y": 0})
    dependencies: list[str] = field(default_factory=list)
    # 节点级生成参数（prompt/model/sampler/...）
    settings: dict[str, Any] = field(default_factory=dict)
    locked: bool = False         # 锁定后不参与 run / review / auto-fix

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "title": self.title,
            "content": self.content,
            "status": self.status.value,
            "agent_note": self.agent_note,
            "human_note": self.human_note,
            "position": self.position,
            "dependencies": self.dependencies,
            "settings": self.settings,
            "locked": self.locked,
        }

    def merge_settings(self, patch: dict[str, Any]) -> None:
        """浅合并 settings；None 值视为删除该键。"""
        if not isinstance(patch, dict):
            return
        for key, value in patch.items():
            if value is None and key in self.settings:
                self.settings.pop(key, None)
            else:
                self.settings[key] = value

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ProductionNode:
        """从 to_dict() 产物反序列化（持久化恢复用）；非法枚举值抛 ValueError。"""
        return cls(
            node_id=raw.get("node_id") or uuid4().hex[:8],
            node_type=NodeType(raw.get("node_type", NodeType.brief_analysis.value)),
            title=raw.get("title", ""),
            content=raw.get("content"),
            status=NodeStatus(raw.get("status", NodeStatus.pending.value)),
            agent_note=raw.get("agent_note", ""),
            human_note=raw.get("human_note", ""),
            position=raw.get("position") or {"x": 0, "y": 0},
            dependencies=raw.get("dependencies") or [],
            settings=raw.get("settings") or {},
            locked=bool(raw.get("locked", False)),
        )


@dataclass
class ProductionCanvas:
    canvas_id: str = field(default_factory=lambda: uuid4().hex)
    title: str = "未命名"
    brief: str = ""
    nodes: list[ProductionNode] = field(default_factory=list)
    workflow_run_id: str | None = None

    def add_node(self, node: ProductionNode) -> ProductionNode:
        self.nodes.append(node)
        return node

    def get_node(self, node_id: str) -> ProductionNode | None:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def update_node(self, node_id: str, **kwargs) -> ProductionNode | None:
        node = self.get_node(node_id)
        if node is None:
            return None
        for k, v in kwargs.items():
            if hasattr(node, k):
                setattr(node, k, v)
        return node

    def apply_layout(
        self,
        positions: list[dict[str, Any]],
        edges: list[dict[str, str]],
    ) -> None:
        """保存节点位置，并把 edges 折算为目标节点 dependencies。"""
        by_id = {n.node_id: n for n in self.nodes}
        for entry in positions:
            node = by_id.get(str(entry.get("node_id", "")))
            if node is None:
                continue
            position = entry.get("position") or {}
            node.position = {
                "x": float(position.get("x", node.position.get("x", 0)) or 0),
                "y": float(position.get("y", node.position.get("y", 0)) or 0),
            }
        deps: dict[str, list[str]] = {n.node_id: [] for n in self.nodes}
        for edge in edges:
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if not source or not target or source == target:
                continue
            if target not in deps or source not in by_id:
                continue
            if source not in deps[target]:
                deps[target].append(source)
        for node_id, dep_list in deps.items():
            node = by_id.get(node_id)
            if node is not None:
                node.dependencies = dep_list

    def to_dict(self) -> dict:
        data: dict[str, Any] = {
            "canvas_id": self.canvas_id,
            "title": self.title,
            "brief": self.brief,
            "nodes": [n.to_dict() for n in self.nodes],
        }
        if self.workflow_run_id:
            data["workflow_run_id"] = self.workflow_run_id
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ProductionCanvas:
        """从 to_dict() 产物反序列化（持久化恢复用）；非法节点静默跳过。"""
        canvas = cls(
            canvas_id=raw.get("canvas_id") or uuid4().hex,
            title=raw.get("title", ""),
            brief=raw.get("brief", ""),
            workflow_run_id=raw.get("workflow_run_id"),
        )
        for node_raw in raw.get("nodes", []):
            try:
                canvas.nodes.append(ProductionNode.from_dict(node_raw))
            except ValueError:
                continue
        return canvas


def media_spec_for_node(node_type: NodeType):
    """batch-generate 的节点类型 → (MediaKind, GenerationMode) 映射。

    关键帧→文生图、视频→文生视频、配音→音频 text_to_speech；
    未映射节点类型返回 None（跳过）。供 api/v1/canvas.py batch-generate 消费，
    避免节点类型判断散落在 API 层。
    """
    from xagent.domains.creative_studio.media.base import GenerationMode, MediaKind

    specs = {
        NodeType.keyframe: (MediaKind.image, GenerationMode.text_to_image),
        NodeType.video: (MediaKind.video, GenerationMode.text_to_video),
        NodeType.voiceover: (MediaKind.audio, GenerationMode.text_to_speech),
    }
    return specs.get(node_type)
