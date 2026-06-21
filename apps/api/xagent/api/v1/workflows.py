"""工作流路由：创建/执行/审批/查看视图。强鉴权 + RBAC + 租户隔离。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.workflow import (
    ApprovalGate,
    WorkflowEngine,
    WorkflowSpec,
    WorkflowStep,
    get_engine,
)
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session
from xagent.infra.repos.workflow import load_workflow_runs, persist_workflow_run

router = APIRouter(prefix="/workflows", tags=["workflows"])


class StepIn(BaseModel):
    id: str
    name: str
    role: str = "general"
    goal: str = ""
    depends_on: list[str] = Field(default_factory=list)
    compensation_role: str | None = None
    compensation_goal: str | None = None
    approver_role: str | None = None
    approval_message: str = ""


class SpecIn(BaseModel):
    name: str
    description: str = ""
    steps: list[StepIn]


def _to_spec(body: SpecIn) -> WorkflowSpec:
    steps = [
        WorkflowStep(
            id=s.id,
            name=s.name,
            role=s.role,
            goal=s.goal,
            depends_on=s.depends_on,
            compensation_role=s.compensation_role,
            compensation_goal=s.compensation_goal,
            approval=ApprovalGate(approver_role=s.approver_role, message=s.approval_message)
            if s.approver_role
            else None,
        )
        for s in body.steps
    ]
    return WorkflowSpec(name=body.name, description=body.description, steps=steps)


@router.post("", summary="创建并启动工作流")
async def create_and_run(
    body: SpecIn,
    principal: Principal = Depends(require_permission("workflow", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    engine: WorkflowEngine = get_engine()
    spec = _to_spec(body)
    run = engine.create_run(spec, principal)
    run = await engine.execute(run.run_id, principal)
    view = run.to_view()
    await persist_workflow_run(session, view)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="workflow.run",
        resource="workflow",
        detail={"run_id": run.run_id, "status": run.status.value},
    )
    return view


@router.get("", summary="列出当前租户工作流（优先 DB 持久化记录）")
async def list_runs(
    principal: Principal = Depends(require_permission("workflow", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    engine = get_engine()
    # 优先返回 DB 持久化记录（跨重启不丢）；DB 空则回退内存
    db_runs = await load_workflow_runs(session, principal.tenant_id)
    if db_runs:
        return {"runs": db_runs, "source": "db"}
    runs = [r.to_view() for r in engine.list_runs(principal.tenant_id)]
    return {"runs": runs, "source": "memory"}


@router.get("/{run_id}", summary="查看工作流结构化视图（timeline）")
async def get_view(
    run_id: str,
    principal: Principal = Depends(require_permission("workflow", "read")),
) -> dict:
    engine = get_engine()
    return engine.replay(run_id, principal)


@router.post("/{run_id}/approve/{step_id}", summary="审批通过")
async def approve(
    run_id: str,
    step_id: str,
    principal: Principal = Depends(require_permission("workflow", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    engine = get_engine()
    run = await engine.approve(run_id, step_id, principal)
    view = run.to_view()
    await persist_workflow_run(session, view)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="workflow.approve",
        resource="workflow",
        detail={"run_id": run_id, "step_id": step_id},
    )
    return view


@router.post("/{run_id}/deny/{step_id}", summary="审批拒绝")
async def deny(
    run_id: str,
    step_id: str,
    principal: Principal = Depends(require_permission("workflow", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    engine = get_engine()
    run = await engine.deny(run_id, step_id, principal)
    view = run.to_view()
    await persist_workflow_run(session, view)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="workflow.deny",
        resource="workflow",
        detail={"run_id": run_id, "step_id": step_id},
    )
    return view
