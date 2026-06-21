"""工作流数据模型 + 结构化视图（护城河）。

StepEvent 贯穿执行/前端 timeline；WorkflowRun.to_view() 产出前端可直接渲染的
结构化视图（步骤卡片 + 状态 + timeline），是 X-Agent 的差异化资产。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class WorkflowStatus(str, Enum):  # noqa: UP042  (兼容 py3.11)
    pending = "pending"
    running = "running"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    failed = "failed"
    rolled_back = "rolled_back"
    cancelled = "cancelled"


class StepStatus(str, Enum):  # noqa: UP042
    pending = "pending"
    running = "running"
    awaiting_approval = "awaiting_approval"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"
    compensated = "compensated"


@dataclass
class ApprovalGate:
    """审批门：执行到此需外部 approve/deny 信号才继续。"""

    approver_role: str = "admin"
    message: str = ""


@dataclass
class WorkflowStep:
    id: str
    name: str
    # 可执行描述：role + goal 交给编排内核（run_agent）执行
    role: str = "general"
    goal: str = ""
    depends_on: list[str] = field(default_factory=list)
    # 补偿动作：失败时回滚用（role+goal 语义）
    compensation_role: str | None = None
    compensation_goal: str | None = None
    approval: ApprovalGate | None = None
    status: StepStatus = StepStatus.pending
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class TimelineEvent:
    """timeline 视图事件。"""

    ts: str
    step_id: str
    kind: str  # started | succeeded | failed | compensated | approval_requested | approved | denied
    detail: Any = None


@dataclass
class WorkflowRun:
    run_id: str
    spec_name: str
    tenant_id: str
    steps: list[WorkflowStep]
    status: WorkflowStatus = WorkflowStatus.pending
    timeline: list[TimelineEvent] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def step(self, step_id: str) -> WorkflowStep:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def add_event(self, step_id: str, kind: str, detail: Any = None) -> TimelineEvent:
        ev = TimelineEvent(ts=self._now(), step_id=step_id, kind=kind, detail=detail)
        self.timeline.append(ev)
        return ev

    def to_view(self) -> dict[str, Any]:
        """结构化视图：前端 timeline / 步骤卡片直接渲染（护城河）。"""
        return {
            "run_id": self.run_id,
            "spec_name": self.spec_name,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "steps": [
                {
                    "id": s.id,
                    "name": s.name,
                    "status": s.status.value,
                    "depends_on": s.depends_on,
                    "has_compensation": s.compensation_goal is not None,
                    "has_approval": s.approval is not None,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "timeline": [
                {"ts": e.ts, "step_id": e.step_id, "kind": e.kind, "detail": e.detail}
                for e in self.timeline
            ],
        }


@dataclass
class WorkflowSpec:
    """工作流定义（用户提交）。"""

    name: str
    steps: list[WorkflowStep]
    description: str = ""
