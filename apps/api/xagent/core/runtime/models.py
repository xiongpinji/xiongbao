"""统一 Runtime 读模型。"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from xagent.core.orchestration.state import RUN_STATUS_PENDING, normalize_run_status
from xagent.core.runtime.policies import normalize_runtime_policy


@dataclass(slots=True)
class RuntimeTaskRef:
    task_id: str
    kind: str
    source: str | None = None
    intent_type: str | None = None
    route_source: str | None = None

    def to_view(self) -> dict[str, str]:
        policy = normalize_runtime_policy(
            {
                "kind": self.kind,
                "source": self.source,
                "intent_type": self.intent_type,
                "route_source": self.route_source,
            }
        )
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "source": policy["source"],
            "intent_type": policy["intent_type"],
            "route_source": policy["route_source"],
        }


@dataclass(slots=True)
class RuntimeRun:
    run_id: str
    task: RuntimeTaskRef
    tenant_id: str
    owner_id: str = ""
    status: str = RUN_STATUS_PENDING
    backend: str = ""
    input_payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None

    def to_view(self) -> dict[str, Any]:
        task_view = self.task.to_view()
        resolved_updated_at = (
            self.updated_at or self.finished_at or self.started_at or self.created_at
        )
        return {
            "task_id": task_view["task_id"],
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
            "kind": task_view["kind"],
            "backend": self.backend,
            "status": normalize_run_status(self.status, default=RUN_STATUS_PENDING),
            "source": task_view["source"],
            "intent_type": task_view["intent_type"],
            "route_source": task_view["route_source"],
            "input": copy.deepcopy(self.input_payload),
            "result": copy.deepcopy(self.result),
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "updated_at": resolved_updated_at,
        }
