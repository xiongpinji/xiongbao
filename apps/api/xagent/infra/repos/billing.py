"""计费 repository：账单明细落库。"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from xagent.infra.logging import get_logger
from xagent.infra.models.billing import BillingRecordORM

logger = get_logger("xagent.repos.billing")


async def persist_billing_record(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    action: str,
    cost: float = 0.0,
    tokens: int = 0,
    detail: dict | None = None,
) -> None:
    try:
        session.add(
            BillingRecordORM(
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                cost=cost,
                tokens=tokens,
                detail=json.dumps(detail or {}, ensure_ascii=False),
            )
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.warning("persist_billing_failed", tenant_id=tenant_id, error=str(exc))


# ─── 同步持久化（供同步接口的 BillingService 使用） ───

from sqlalchemy import delete, select  # noqa: E402

from xagent.infra.models.billing import SubscriptionORM, TenantUsageORM  # noqa: E402
from xagent.infra.repos.sync_db import sync_session  # noqa: E402


def get_or_create_subscription_sync(tenant_id: str) -> dict:
    """取订阅；不存在则按 free 档创建。返回 {tenant_id, plan, period_start}。"""
    with sync_session() as s:
        row = s.get(SubscriptionORM, tenant_id)
        if row is None:
            row = SubscriptionORM(tenant_id=tenant_id, plan="free")
            s.add(row)
            s.flush()
        return {
            "tenant_id": row.tenant_id,
            "plan": row.plan,
            "period_start": row.period_start,
        }


def set_plan_sync(tenant_id: str, plan: str) -> dict:
    with sync_session() as s:
        row = s.get(SubscriptionORM, tenant_id)
        if row is None:
            row = SubscriptionORM(tenant_id=tenant_id, plan=plan)
            s.add(row)
        else:
            row.plan = plan
        s.flush()
        return {
            "tenant_id": row.tenant_id,
            "plan": row.plan,
            "period_start": row.period_start,
        }


def usage_sync(tenant_id: str) -> dict:
    """读租户用量计数（tenant_usage 表，不存在视为零用量）。"""
    with sync_session() as s:
        row = s.get(TenantUsageORM, tenant_id)
        if row is None:
            return {"agent_runs": 0, "media_generations": 0, "tokens": 0}
        return {
            "agent_runs": row.agent_runs,
            "media_generations": row.media_generations,
            "tokens": row.tokens,
        }


def consume_sync(
    tenant_id: str,
    *,
    actor: str,
    action: str,
    tokens: int = 0,
    cost: float = 0.0,
    max_agent_runs: int,
    max_media_generations: int,
    max_tokens: int,
) -> dict:
    """配额校验 + 用量扣减 + 账单流水，单事务。超限抛 ValueError（回滚）。"""
    with sync_session() as s:
        row = s.get(TenantUsageORM, tenant_id)
        if row is None:
            row = TenantUsageORM(tenant_id=tenant_id)
            s.add(row)
            s.flush()
        if action == "agent.run":
            if row.agent_runs >= max_agent_runs:
                raise ValueError(
                    f"配额超限：agent.run ({row.agent_runs}/{max_agent_runs})"
                )
            row.agent_runs += 1
        elif action == "media.generate":
            if row.media_generations >= max_media_generations:
                raise ValueError(
                    "配额超限：media.generate "
                    f"({row.media_generations}/{max_media_generations})"
                )
            row.media_generations += 1
        if row.tokens + tokens > max_tokens:
            raise ValueError(f"配额超限：tokens ({row.tokens + tokens}/{max_tokens})")
        row.tokens += tokens
        s.add(
            BillingRecordORM(
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                cost=cost,
                tokens=tokens,
                detail="{}",
            )
        )
        s.flush()
        return {
            "agent_runs": row.agent_runs,
            "media_generations": row.media_generations,
            "tokens": row.tokens,
        }


def list_records_sync(tenant_id: str) -> list[dict]:
    with sync_session() as s:
        rows = (
            s.execute(
                select(BillingRecordORM)
                .where(BillingRecordORM.tenant_id == tenant_id)
                .order_by(BillingRecordORM.id.asc())
            )
            .scalars()
            .all()
        )
        return [
            {
                "ts": r.ts,
                "actor": r.actor,
                "action": r.action,
                "cost": r.cost,
                "tokens": r.tokens,
                "detail": json.loads(r.detail) if r.detail else {},
            }
            for r in rows
        ]


def wipe_billing_sync() -> None:
    """清空计费表（仅测试隔离用：reset_billing_service 调用）。"""
    with sync_session() as s:
        s.execute(delete(BillingRecordORM))
        s.execute(delete(TenantUsageORM))
        s.execute(delete(SubscriptionORM))
