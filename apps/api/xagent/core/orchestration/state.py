"""编排状态与事件。StepEvent 序列即「工作流结构化视图」的数据源（护城河）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from xagent.adapters.llm import Message

RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_AWAITING_APPROVAL = "awaiting_approval"
RUN_STATUS_SUCCEEDED = "succeeded"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_CANCELLED = "cancelled"
RUN_STATUS_ROLLED_BACK = "rolled_back"

RUN_STATUS_VALUES = frozenset(
    {
        RUN_STATUS_PENDING,
        RUN_STATUS_RUNNING,
        RUN_STATUS_AWAITING_APPROVAL,
        RUN_STATUS_SUCCEEDED,
        RUN_STATUS_FAILED,
        RUN_STATUS_CANCELLED,
        RUN_STATUS_ROLLED_BACK,
    }
)

_LEGACY_RUN_STATUS_MAP = {
    "completed": RUN_STATUS_SUCCEEDED,
    "queued": RUN_STATUS_PENDING,
    "started": RUN_STATUS_RUNNING,
    "success": RUN_STATUS_SUCCEEDED,
    "failure": RUN_STATUS_FAILED,
    "produced": RUN_STATUS_SUCCEEDED,
    "partial": RUN_STATUS_FAILED,
}


def normalize_run_status(status: str | None, *, default: str = RUN_STATUS_PENDING) -> str:
    normalized_default = (default or RUN_STATUS_PENDING).strip().lower()
    normalized_default = _LEGACY_RUN_STATUS_MAP.get(normalized_default, normalized_default)
    if normalized_default not in RUN_STATUS_VALUES:
        normalized_default = RUN_STATUS_PENDING
    normalized = (status or normalized_default).strip().lower()
    normalized = _LEGACY_RUN_STATUS_MAP.get(normalized, normalized)
    return normalized if normalized in RUN_STATUS_VALUES else normalized_default


class StepKind(str, Enum):  # noqa: UP042  (兼容 py3.11)
    reason = "reason"      # LLM 推理
    tool_call = "tool_call"
    tool_result = "tool_result"
    final = "final"
    error = "error"
    token = "token"        # 流式逐 token 输出
    progress = "progress"  # 执行进度估算


@dataclass
class StepEvent:
    kind: StepKind
    content: Any = None
    tool: str | None = None
    step: int = 0
    trace_id: str = ""  # 链路追踪 ID：格式 step-{step}-{seq}


@dataclass
class AgentState:
    goal: str
    role_name: str
    tenant_id: str
    messages: list[Message] = field(default_factory=list)
    step: int = 0
    finished: bool = False
    final_answer: str = ""
    # ── Token 用量追踪（对标 Codex usage 统计） ──
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0


@dataclass
class AgentRun:
    """一次 agent 运行的结果，含事件序列（供 timeline 视图 / 审计）。"""

    run_id: str
    goal: str
    role_name: str
    tenant_id: str
    final_answer: str
    steps: int
    events: list[StepEvent] = field(default_factory=list)
    conversation_id: str = ""
    # ── Token 用量（实测成本追踪） ──
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "role": self.role_name,
            "tenant_id": self.tenant_id,
            "final_answer": self.final_answer,
            "steps": self.steps,
            "conversation_id": self.conversation_id,
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
            },
            "events": [
                {"kind": e.kind.value, "tool": e.tool, "step": e.step, "content": e.content}
                for e in self.events
            ],
        }
