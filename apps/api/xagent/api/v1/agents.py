"""Agent 路由：运行 agent 任务、列出角色。

安全：execute 需 agent:execute 权限；运行结果写审计链；租户来自 principal，
调用方无法伪造（不从 body 取 tenant_id）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.agents import get_role_registry
from xagent.core.orchestration import run_agent
from xagent.domains.billing import get_billing_service
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session
from xagent.infra.repos.billing import persist_billing_record

router = APIRouter(prefix="/agents", tags=["agents"])


class RunRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="任务目标")
    role: str | None = Field(None, description="指定角色名；不指定则按能力匹配")
    capabilities: list[str] = Field(default_factory=list, description="任务所需能力标签")
    model: str | None = None


@router.get("/roles", summary="列出可用 agent 角色")
async def list_roles(
    principal: Principal = Depends(require_permission("agent", "read")),
) -> dict:
    roles = get_role_registry().all()
    return {
        "roles": [
            {
                "name": r.name,
                "description": r.description,
                "capabilities": sorted(r.capabilities),
            }
            for r in roles
        ]
    }


@router.post("/run", summary="运行一次 agent 任务")
async def run(
    body: RunRequest,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # 计费：配额校验 + 用量累计
    billing = get_billing_service()
    try:
        billing.check_and_consume(
            principal.tenant_id,
            actor=principal.user_id,
            action="agent.run",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        ) from exc

    result = await run_agent(
        body.goal,
        principal=principal,
        role_name=body.role,
        capabilities=set(body.capabilities) or None,
        model=body.model,
    )
    # 账单落库（best-effort）
    await persist_billing_record(
        session,
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="agent.run",
        cost=0.0,
        tokens=result.steps,
        detail={"run_id": result.run_id, "role": result.role_name},
    )
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="agent.run",
        resource="agent",
        detail={"run_id": result.run_id, "role": result.role_name, "steps": result.steps},
    )
    return result.to_dict()
