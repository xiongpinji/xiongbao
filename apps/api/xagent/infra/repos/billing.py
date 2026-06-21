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
