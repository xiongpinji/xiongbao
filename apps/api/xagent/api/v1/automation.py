"""API v1: 多 Agent 并行 + 技能系统 + 定时调度。

对标 Codex/Hermes 高级能力的 HTTP 接口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from xagent.core.orchestration.parallel import SubTask, run_parallel_agents
from xagent.core.orchestration.supervisor import run_supervisor
from xagent.core.scheduler import get_scheduler
from xagent.core.skills import get_skill_store
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(tags=["automation"])


# ─── 多 Agent 并行 ───


class ParallelRunIn(BaseModel):
    tasks: list[dict] = Field(..., min_length=1, max_length=5)
    coordinator_goal: str = ""


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
        sub_tasks, principal, coordinator_goal=body.coordinator_goal
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
        body.goal, principal, roles=body.roles or None,
    )
    return result.to_dict()


# ─── 技能系统 ───


class SkillCreateIn(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    trigger_pattern: str = ""
    steps: list[dict] = Field(default_factory=list)
    system_prompt_hint: str = ""
    tags: list[str] = Field(default_factory=list)


@router.get("/skills", summary="列出所有技能")
async def list_skills(
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    store = get_skill_store()
    return {"skills": [s.to_dict() for s in store.list_all()]}


@router.post("/skills", summary="创建技能")
async def create_skill(
    body: SkillCreateIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    store = get_skill_store()
    skill = store.create_skill(
        name=body.name,
        description=body.description,
        trigger_pattern=body.trigger_pattern,
        steps=body.steps,
        system_prompt_hint=body.system_prompt_hint,
        tags=body.tags,
    )
    return skill.to_dict()


@router.delete("/skills/{skill_id}", summary="删除技能")
async def delete_skill(
    skill_id: str,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    store = get_skill_store()
    deleted = store.delete(skill_id)
    return {"deleted": deleted}


@router.get("/skills/match", summary="匹配技能")
async def match_skills(
    goal: str,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    store = get_skill_store()
    matched = store.match(goal)
    return {"matched": [s.to_dict() for s in matched]}


# ─── 定时调度 ───


class JobCreateIn(BaseModel):
    name: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    role: str | None = None
    cron_expr: str = ""
    interval_seconds: int = 0


@router.get("/scheduler/jobs", summary="列出定时任务")
async def list_jobs(
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    scheduler = get_scheduler()
    return {"jobs": [j.to_dict() for j in scheduler.list_jobs()]}


@router.post("/scheduler/jobs", summary="创建定时任务")
async def create_job(
    body: JobCreateIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    scheduler = get_scheduler()
    job = scheduler.add_job(
        name=body.name,
        goal=body.goal,
        role=body.role,
        cron_expr=body.cron_expr,
        interval_seconds=body.interval_seconds,
        tenant_id=principal.tenant_id,
        owner_id=principal.user_id,
    )
    return job.to_dict()


@router.delete("/scheduler/jobs/{job_id}", summary="删除定时任务")
async def delete_job(
    job_id: str,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    scheduler = get_scheduler()
    deleted = scheduler.remove_job(job_id)
    return {"deleted": deleted}


@router.patch("/scheduler/jobs/{job_id}/toggle", summary="启用/禁用定时任务")
async def toggle_job(
    job_id: str,
    enabled: bool = True,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    scheduler = get_scheduler()
    job = scheduler.toggle_job(job_id, enabled)
    if not job:
        return {"error": "job not found"}
    return job.to_dict()
