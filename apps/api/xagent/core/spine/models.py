from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


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


@dataclass(slots=True)
class Initiative:
    initiative_id: str
    goal_id: str
    tenant_id: str
    title: str
    status: str = "pending"
    priority: str = "medium"
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


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
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
