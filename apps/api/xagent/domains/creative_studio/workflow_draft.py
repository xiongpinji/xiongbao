"""一句话 brief → 待审核生产工作流草稿（节点链）。

移植自旧仓 creative_studio/workflow_draft.py 思路，重写为纯净版。
节点链：需求解析 → 钩子结构 → 分镜 → 角色一致性 → 关键帧(image) →
视频(video) → 人工审核导出。每节点带 agent_role / provider_kind / risk_level /
成本/耗时估算，供前端 ComfyUI 风格画布渲染（Phase 4 用 React Flow）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class NodeRisk(str, Enum):  # noqa: UP042
    low = "low"
    medium = "medium"
    high = "high"


class ProviderKind(str, Enum):  # noqa: UP042
    llm = "llm"
    image = "image"
    video = "video"
    audio = "audio"
    review = "review"


@dataclass
class WorkflowDraftNode:
    node_id: str
    node_type: str
    agent_role: str
    provider_kind: ProviderKind
    risk_level: NodeRisk = NodeRisk.low
    estimated_cost: float = 0.0
    estimated_seconds: float = 0.0
    needs_review: bool = False
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDraft:
    draft_id: str
    brief: str
    genre: str
    platform: str
    target_duration_seconds: float
    nodes: list[WorkflowDraftNode]
    status: str = "pending_review"  # pending_review | approved | rejected

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "brief": self.brief,
            "genre": self.genre,
            "platform": self.platform,
            "target_duration_seconds": self.target_duration_seconds,
            "status": self.status,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type,
                    "agent_role": n.agent_role,
                    "provider_kind": n.provider_kind.value,
                    "risk_level": n.risk_level.value,
                    "estimated_cost": n.estimated_cost,
                    "estimated_seconds": n.estimated_seconds,
                    "needs_review": n.needs_review,
                    "params": n.params,
                }
                for n in self.nodes
            ],
        }


def build_draft_from_brief(
    brief: str,
    *,
    genre: str = "逆袭",
    platform: str = "抖音",
    target_duration_seconds: float = 60.0,
) -> WorkflowDraft:
    """据一句话 brief 生成待审核工作流草稿（节点链）。

    Phase 3：用确定性模板生成节点链；后续可接 LLM 做题材/钩子细化。
    """
    nodes = [
        WorkflowDraftNode(
            node_id="n_brief",
            node_type="需求解析",
            agent_role="planner",
            provider_kind=ProviderKind.llm,
            risk_level=NodeRisk.low,
            estimated_seconds=2,
        ),
        WorkflowDraftNode(
            node_id="n_hook",
            node_type="钩子结构",
            agent_role="researcher",
            provider_kind=ProviderKind.llm,
            risk_level=NodeRisk.medium,
            estimated_seconds=3,
            params={"slots": ["黄金3秒钩子", "反转", "悬念收尾"]},
        ),
        WorkflowDraftNode(
            node_id="n_storyboard",
            node_type="分镜",
            agent_role="planner",
            provider_kind=ProviderKind.llm,
            estimated_seconds=4,
            params={"shot_count_range": [3, 12]},
        ),
        WorkflowDraftNode(
            node_id="n_character",
            node_type="角色一致性",
            agent_role="researcher",
            provider_kind=ProviderKind.image,
            risk_level=NodeRisk.medium,
            estimated_cost=0.2,
            estimated_seconds=8,
            params={"reference_strategy": "fixed_lora+seed"},
        ),
        WorkflowDraftNode(
            node_id="n_keyframe",
            node_type="关键帧",
            agent_role="general",
            provider_kind=ProviderKind.image,
            estimated_cost=0.3,
            estimated_seconds=15,
        ),
        WorkflowDraftNode(
            node_id="n_video",
            node_type="视频",
            agent_role="general",
            provider_kind=ProviderKind.video,
            risk_level=NodeRisk.high,
            estimated_cost=1.2,
            estimated_seconds=30,
        ),
        WorkflowDraftNode(
            node_id="n_review",
            node_type="人工审核导出",
            agent_role="general",
            provider_kind=ProviderKind.review,
            needs_review=True,
            estimated_seconds=0,
        ),
    ]
    return WorkflowDraft(
        draft_id=uuid4().hex,
        brief=brief,
        genre=genre,
        platform=platform,
        target_duration_seconds=target_duration_seconds,
        nodes=nodes,
    )
