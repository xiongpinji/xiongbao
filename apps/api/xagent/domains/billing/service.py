"""计费服务：订阅管理 + 配额校验 + 用量累计。按租户隔离。

持久化策略（Phase 5 持久化改造）：
- DB 优先：订阅落 subscriptions 表，用量从 billing_records 表聚合，
  记账写 billing_records 表 —— 重启数据不丢。
- DB 不可用（如无 DB 的极端 lite 场景）时自动降级为进程内存实现，
  API 契约不变。
- 对外接口保持同步（路由/测试同步调用），底层走同步 SQLAlchemy
  （infra.repos.sync_db）。
"""

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
from xagent.infra.logging import get_logger

logger = get_logger("xagent.billing")


@dataclass
class TenantUsage:
    agent_runs: int = 0
    media_generations: int = 0
    tokens: int = 0


class BillingService:
    def __init__(self) -> None:
        # DB 可用性标记：首次 DB 操作失败后降级内存，不再反复尝试
        self._db_ok = True
        # 内存降级存储（仅 _db_ok=False 时使用）
        self._subs: dict[str, Subscription] = {}
        self._usage: dict[str, TenantUsage] = {}
        self._records: list[BillingRecord] = []

    # ─── 内部：DB 降级处理 ───

    def _degrade(self, op: str, exc: Exception) -> None:
        if self._db_ok:
            self._db_ok = False
            logger.warning("billing_db_degraded", op=op, error=str(exc))

    # ─── 订阅 ───

    def get_subscription(self, tenant_id: str) -> Subscription:
        if self._db_ok:
            try:
                from xagent.infra.repos.billing import get_or_create_subscription_sync

                row = get_or_create_subscription_sync(tenant_id)
                return Subscription(
                    tenant_id=row["tenant_id"],
                    plan=Plan(row["plan"]),
                    period_start=row["period_start"],
                )
            except Exception as exc:
                self._degrade("get_subscription", exc)
        return self._subs.setdefault(tenant_id, Subscription(tenant_id=tenant_id))

    def set_plan(self, tenant_id: str, plan: Plan) -> Subscription:
        if self._db_ok:
            try:
                from xagent.infra.repos.billing import set_plan_sync

                row = set_plan_sync(tenant_id, plan.value)
                return Subscription(
                    tenant_id=row["tenant_id"],
                    plan=Plan(row["plan"]),
                    period_start=row["period_start"],
                )
            except Exception as exc:
                self._degrade("set_plan", exc)
        sub = self.get_subscription(tenant_id)
        sub.plan = plan
        return sub

    def quota(self, tenant_id: str) -> UsageQuota:
        return PLAN_QUOTA[self.get_subscription(tenant_id).plan]

    # ─── 用量 ───

    def usage(self, tenant_id: str) -> TenantUsage:
        if self._db_ok:
            try:
                from xagent.infra.repos.billing import usage_sync

                u = usage_sync(tenant_id)
                return TenantUsage(
                    agent_runs=u["agent_runs"],
                    media_generations=u["media_generations"],
                    tokens=u["tokens"],
                )
            except Exception as exc:
                self._degrade("usage", exc)
        return self._usage.setdefault(tenant_id, TenantUsage())

    def check_and_consume(
        self, tenant_id: str, *, actor: str, action: str, tokens: int = 0, cost: float = 0.0
    ) -> None:
        """超限抛 ValueError；通过则累计用量并记账。"""
        if self._db_ok:
            try:
                from xagent.infra.repos.billing import consume_sync

                sub = self.get_subscription(tenant_id)
                quota = PLAN_QUOTA[sub.plan]
                consume_sync(
                    tenant_id,
                    actor=actor,
                    action=action,
                    tokens=tokens,
                    cost=cost,
                    max_agent_runs=quota.max_agent_runs,
                    max_media_generations=quota.max_media_generations,
                    max_tokens=quota.max_tokens,
                )
                return
            except ValueError:
                raise
            except Exception as exc:
                self._degrade("check_and_consume", exc)
        # 内存降级路径
        sub = self.get_subscription(tenant_id)
        quota = PLAN_QUOTA[sub.plan]
        usage = self._usage.setdefault(tenant_id, TenantUsage())
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
        if self._db_ok:
            try:
                from xagent.infra.repos.billing import list_records_sync

                return [
                    BillingRecord(
                        tenant_id=tenant_id,
                        actor=r["actor"],
                        action=r["action"],
                        cost=r["cost"],
                        tokens=r["tokens"],
                        ts=r["ts"],
                        detail=r["detail"],
                    )
                    for r in list_records_sync(tenant_id)
                ]
            except Exception as exc:
                self._degrade("records", exc)
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
    """重置单例；并尽力清空计费表（测试隔离用，生产无人调用）。

    测试环境下 DB 文件跨 pytest 运行持久存在，若不清表会造成
    usage/plan 断言被上一轮残留污染。清表失败（如表不存在）静默忽略。
    """
    get_billing_service.cache_clear()
    try:
        from xagent.infra.repos.billing import wipe_billing_sync

        wipe_billing_sync()
    except Exception:  # noqa: S110
        pass
