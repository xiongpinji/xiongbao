"""计费服务：订阅管理 + 配额校验 + 用量累计。按租户隔离。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from xagent.domains.billing.models import (
    PLAN_QUOTA,
    BillingRecord,
    Plan,
    Subscription,
    UsageQuota,
)


@dataclass
class TenantUsage:
    agent_runs: int = 0
    media_generations: int = 0
    tokens: int = 0


class BillingService:
    def __init__(self) -> None:
        self._subs: dict[str, Subscription] = {}
        self._usage: dict[str, TenantUsage] = {}
        self._records: list[BillingRecord] = []

    def get_subscription(self, tenant_id: str) -> Subscription:
        return self._subs.setdefault(tenant_id, Subscription(tenant_id=tenant_id))

    def set_plan(self, tenant_id: str, plan: Plan) -> Subscription:
        sub = self.get_subscription(tenant_id)
        sub.plan = plan
        return sub

    def quota(self, tenant_id: str) -> UsageQuota:
        return PLAN_QUOTA[self.get_subscription(tenant_id).plan]

    def usage(self, tenant_id: str) -> TenantUsage:
        return self._usage.setdefault(tenant_id, TenantUsage())

    def check_and_consume(
        self, tenant_id: str, *, actor: str, action: str, tokens: int = 0, cost: float = 0.0
    ) -> None:
        """超限抛 ValueError；通过则累计用量并记账。"""
        sub = self.get_subscription(tenant_id)
        quota = PLAN_QUOTA[sub.plan]
        usage = self.usage(tenant_id)
        if action == "agent.run":
            if usage.agent_runs >= quota.max_agent_runs:
                raise ValueError(f"配额超限：agent.run ({usage.agent_runs}/{quota.max_agent_runs})")
            usage.agent_runs += 1
        elif action == "media.generate":
            if usage.media_generations >= quota.max_media_generations:
                raise ValueError(
                    "配额超限：media.generate "
                    f"({usage.media_generations}/{quota.max_media_generations})"
                )
            usage.media_generations += 1
        usage.tokens += tokens
        if usage.tokens > quota.max_tokens:
            raise ValueError(f"配额超限：tokens ({usage.tokens}/{quota.max_tokens})")
        self._records.append(
            BillingRecord(
                tenant_id=tenant_id, actor=actor, action=action, cost=cost, tokens=tokens
            )
        )

    def records(self, tenant_id: str) -> list[BillingRecord]:
        return [r for r in self._records if r.tenant_id == tenant_id]

    def summary(self, tenant_id: str) -> dict:
        sub = self.get_subscription(tenant_id)
        u = self.usage(tenant_id)
        q = PLAN_QUOTA[sub.plan]
        return {
            "tenant_id": tenant_id,
            "plan": sub.plan.value,
            "usage": {
                "agent_runs": u.agent_runs,
                "media_generations": u.media_generations,
                "tokens": u.tokens,
            },
            "quota": {
                "max_agent_runs": q.max_agent_runs,
                "max_media_generations": q.max_media_generations,
                "max_tokens": q.max_tokens,
            },
            "records_count": len(self.records(tenant_id)),
        }


@lru_cache
def get_billing_service() -> BillingService:
    return BillingService()


def reset_billing_service() -> None:
    get_billing_service.cache_clear()
