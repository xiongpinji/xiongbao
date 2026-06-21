"""计费路由：订阅/用量/账单。强鉴权 + RBAC（计费管理需 admin）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from xagent.domains.billing import Plan, get_billing_service
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/billing", tags=["billing"])


class PlanIn(BaseModel):
    plan: Plan


@router.get("/summary", summary="当前租户用量与配额")
async def summary(
    principal: Principal = Depends(require_permission("billing", "read")),
) -> dict:
    return get_billing_service().summary(principal.tenant_id)


@router.post("/plan", summary="设置订阅档位（需 admin）")
async def set_plan(
    body: PlanIn,
    principal: Principal = Depends(require_permission("billing", "manage")),
) -> dict:
    get_billing_service().set_plan(principal.tenant_id, body.plan)
    return get_billing_service().summary(principal.tenant_id)


@router.get("/records", summary="账单明细")
async def records(
    principal: Principal = Depends(require_permission("billing", "read")),
) -> dict:
    recs = get_billing_service().records(principal.tenant_id)
    return {
        "records": [
            {
                "ts": r.ts.isoformat(),
                "actor": r.actor,
                "action": r.action,
                "cost": r.cost,
                "tokens": r.tokens,
                "detail": r.detail,
            }
            for r in recs
        ]
    }
