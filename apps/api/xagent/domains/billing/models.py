"""计费数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class Plan(str, Enum):  # noqa: UP042
    free = "free"
    pro = "pro"
    enterprise = "enterprise"


# 各档配额（每月）
PLAN_QUOTA: dict[Plan, UsageQuota] = {}


@dataclass
class UsageQuota:
    max_agent_runs: int
    max_media_generations: int
    max_tokens: int


PLAN_QUOTA[Plan.free] = UsageQuota(
    max_agent_runs=100, max_media_generations=10, max_tokens=200_000
)
PLAN_QUOTA[Plan.pro] = UsageQuota(
    max_agent_runs=10_000, max_media_generations=500, max_tokens=5_000_000
)
PLAN_QUOTA[Plan.enterprise] = UsageQuota(
    max_agent_runs=1_000_000, max_media_generations=100_000, max_tokens=1_000_000_000
)


@dataclass
class Subscription:
    tenant_id: str
    plan: Plan = Plan.free
    period_start: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BillingRecord:
    tenant_id: str
    actor: str
    action: str
    cost: float
    tokens: int = 0
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    detail: dict = field(default_factory=dict)
