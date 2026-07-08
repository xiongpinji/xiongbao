from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _to_dict(instance: Any) -> dict[str, Any]:
    return {
        item.name: _serialize_value(getattr(instance, item.name))
        for item in fields(instance)
    }


class SpinePhase(str, Enum):  # noqa: UP042
    planning = "planning"
    execution = "execution"
    review = "review"
    release = "release"
    deploy = "deploy"
    recovery = "recovery"
    archive = "archive"


class GoalStatus(str, Enum):  # noqa: UP042
    pending = "pending"
    active = "active"
    blocked = "blocked"
    delivered = "delivered"
    archived = "archived"


@dataclass(slots=True)
class Goal:
    goal_id: str
    tenant_id: str
    owner_id: str
    title: str
    description: str
    phase: SpinePhase = SpinePhase.planning
    status: GoalStatus = GoalStatus.pending
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(slots=True)
class Initiative:
    initiative_id: str
    goal_id: str
    tenant_id: str
    title: str
    status: str = "pending"
    priority: str = "medium"
    position: int = 0
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(slots=True)
class DeliveryTask:
    task_id: str
    initiative_id: str
    goal_id: str
    tenant_id: str
    title: str
    detail: str
    status: str = "ready"
    task_kind: str = "execution"
    run_id: str = ""
    blocker_reason: str = ""
    position: int = 0
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)
