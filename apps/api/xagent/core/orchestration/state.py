"""编排状态与事件。StepEvent 序列即「工作流结构化视图」的数据源（护城河）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from xagent.adapters.llm import Message


class StepKind(str, Enum):  # noqa: UP042  (兼容 py3.11)
    reason = "reason"      # LLM 推理
    tool_call = "tool_call"
    tool_result = "tool_result"
    final = "final"
    error = "error"


@dataclass
class StepEvent:
    kind: StepKind
    content: Any = None
    tool: str | None = None
    step: int = 0


@dataclass
class AgentState:
    goal: str
    role_name: str
    tenant_id: str
    messages: list[Message] = field(default_factory=list)
    step: int = 0
    finished: bool = False
    final_answer: str = ""


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

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "role": self.role_name,
            "tenant_id": self.tenant_id,
            "final_answer": self.final_answer,
            "steps": self.steps,
            "events": [
                {"kind": e.kind.value, "tool": e.tool, "step": e.step, "content": e.content}
                for e in self.events
            ],
        }
