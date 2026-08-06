"""API v1: 多 Agent 并行 + 技能系统 + 定时调度。

对标 Codex/Hermes 高级能力的 HTTP 接口。
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.orchestration.parallel import SubTask, run_parallel_agents
from xagent.core.orchestration.supervisor import run_supervisor
from xagent.domains.scheduled_jobs import (
    ScheduledJobCreate,
    create_scheduled_job,
    delete_scheduled_job,
    get_scheduled_job,
    list_scheduled_job_runs,
    list_scheduled_jobs,
    set_scheduled_job_enabled,
)
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session

router = APIRouter(tags=["automation"])


# ─── 多 Agent 并行 ───


class ParallelRunIn(BaseModel):
    tasks: list[dict] = Field(..., min_length=1, max_length=5)
    coordinator_goal: str = ""
    use_worktrees: bool = Field(
        default=False,
        description="git worktree 隔离：每子代理独立工作区执行，结果附 diff（需 git 仓库）",
    )


@router.post("/agents/parallel-run", summary="多 Agent 并行执行")
async def parallel_run(
    body: ParallelRunIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    sub_tasks = [
        SubTask(
            goal=t.get("goal", ""),
            role=t.get("role"),
            capabilities=t.get("capabilities", []),
        )
        for t in body.tasks
        if t.get("goal")
    ]
    if not sub_tasks:
        return {"error": "至少需要一个有效子任务"}
    result = await run_parallel_agents(
        sub_tasks,
        principal,
        coordinator_goal=body.coordinator_goal,
        use_worktrees=body.use_worktrees,
    )
    return result.to_dict()


class SupervisorRunIn(BaseModel):
    goal: str = Field(..., min_length=1)
    roles: list[str] = Field(default_factory=list)


@router.post("/agents/supervisor-run", summary="Supervisor 多 Agent 协作")
async def supervisor_run(
    body: SupervisorRunIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    """Supervisor 模式：自动分解任务 → 并行分发 → 综合结果。"""
    result = await run_supervisor(
        body.goal,
        principal,
        roles=body.roles or None,
    )
    return result.to_dict()


# ─── 技能系统 ───
# 技能的 CRUD/匹配路由由 skills.py 统一提供（含 404 处理与 system:read/manage 权限），
# 此处不再重复注册，避免路由 shadow（先注册者胜）。


# ─── 定时调度 ───


class JobCreateIn(BaseModel):
    name: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    role: str | None = None
    cron_expr: str = ""
    interval_seconds: int = 0
    max_retries: int = Field(3, ge=0, le=10)
    retry_backoff_seconds: int = Field(60, ge=1, le=86_400)


class JobToggleIn(BaseModel):
    confirm_job_id: str = Field(min_length=1)
    enabled: bool


class JobDeleteIn(BaseModel):
    confirm_job_id: str = Field(min_length=1)


def _confirm_job(job_id: str, confirmed: str) -> None:
    if confirmed != job_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "确认的 Job ID 与路径不一致")


def _audit_job(principal: Principal, action: str, job_id: str) -> None:
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action=f"scheduler.{action}",
        resource="scheduled_job",
        detail={"job_id": job_id},
    )


def _interval(body: JobCreateIn) -> int:
    if body.interval_seconds > 0:
        return body.interval_seconds
    if body.cron_expr.startswith("*/"):
        try:
            return max(60, int(body.cron_expr.split()[0][2:]) * 60)
        except (ValueError, IndexError):
            pass
    return 3600


@router.get("/scheduler/jobs", summary="列出定时任务")
async def list_jobs(
    principal: Principal = Depends(require_permission("agent", "read")),
    session: AsyncSession = Depends(get_session),
):
    return {
        "jobs": [asdict(job) for job in await list_scheduled_jobs(session, principal.tenant_id)]
    }


@router.post("/scheduler/jobs", summary="创建定时任务")
async def create_job(
    body: JobCreateIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
):
    interval = _interval(body)
    job = await create_scheduled_job(
        session,
        ScheduledJobCreate(
            job_id=uuid.uuid4().hex[:12],
            tenant_id=principal.tenant_id,
            owner_id=principal.user_id,
            name=body.name,
            goal=body.goal,
            role=body.role or "",
            cron_expr=body.cron_expr,
            interval_seconds=interval,
            next_run=datetime.now(UTC) + timedelta(seconds=interval),
            max_retries=body.max_retries,
            retry_backoff_seconds=body.retry_backoff_seconds,
        ),
    )
    await session.commit()
    _audit_job(principal, "create", job.job_id)
    return asdict(job)


@router.delete("/scheduler/jobs/{job_id}", summary="删除定时任务")
async def delete_job(
    job_id: str,
    body: JobDeleteIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
):
    _confirm_job(job_id, body.confirm_job_id)
    deleted = await delete_scheduled_job(session, principal.tenant_id, job_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "调度任务不存在")
    await session.commit()
    _audit_job(principal, "delete", job_id)
    return {"deleted": True}


@router.patch("/scheduler/jobs/{job_id}/toggle", summary="启用/禁用定时任务")
async def toggle_job(
    job_id: str,
    body: JobToggleIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
):
    _confirm_job(job_id, body.confirm_job_id)
    job = await set_scheduled_job_enabled(session, principal.tenant_id, job_id, body.enabled)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "调度任务不存在")
    await session.commit()
    _audit_job(principal, "toggle", job_id)
    return asdict(job)


@router.get("/scheduler/jobs/{job_id}/runs", summary="查询调度运行历史")
async def list_job_runs(
    job_id: str,
    principal: Principal = Depends(require_permission("agent", "read")),
    session: AsyncSession = Depends(get_session),
):
    if await get_scheduled_job(session, principal.tenant_id, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "调度任务不存在")
    runs = await list_scheduled_job_runs(session, principal.tenant_id, job_id)
    return {"runs": [asdict(run) for run in runs]}


# ─── 策略自适应 ───


class StrategyIn(BaseModel):
    goal: str = Field(..., min_length=1)
    context: str = ""


@router.post("/agents/strategy-select", summary="智能策略选择")
async def strategy_select(
    body: StrategyIn,
    principal: Principal = Depends(require_permission("agent", "execute")),  # noqa: ARG001
):
    from xagent.core.intelligence import get_strategy_selector

    selector = get_strategy_selector()
    result = selector.select_with_confidence(body.goal, context=body.context)
    return result
