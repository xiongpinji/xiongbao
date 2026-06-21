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
        }


@dataclass
class ProductionCanvas:
    canvas_id: str = field(default_factory=lambda: uuid4().hex)
    title: str = "未命名"
    brief: str = ""
    nodes: list[ProductionNode] = field(default_factory=list)

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

    def to_dict(self) -> dict:
        return {
            "canvas_id": self.canvas_id,
            "title": self.title,
            "brief": self.brief,
            "nodes": [n.to_dict() for n in self.nodes],
        }