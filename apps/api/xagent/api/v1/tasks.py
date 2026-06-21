"""后台任务路由：提交 agent 运行为异步任务 + 查询状态。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from xagent.core.orchestration import run_agent
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.worker import get_task_runner

router = APIRouter(prefix="/tasks", tags=["tasks"])

# task_id -> tenant_id 映射（跨进程安全：Celery 任务也记录，poll 时校验租户）
_task_tenants: dict[str, str] = {}


class TaskSubmitIn(BaseModel):
    goal: str = Field(..., min_length=1)
    role: str | None = None
    capabilities: list[str] = Field(default_factory=list)


@router.post("", summary="提交 agent 运行为后台任务")
async def submit_task(
    body: TaskSubmitIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
) -> dict:
    runner = get_task_runner()

    async def _run():
        return (
            await run_agent(
                body.goal,
                principal=principal,
                role_name=body.role,
                capabilities=set(body.capabilities) or None,
            )
        ).to_dict()

    # full 模式 + Celery 可用 -> 走 Celery；否则进程内
    try:
        from celery import Celery

        from xagent.infra.settings import get_settings

        broker = get_settings().cache.redis_url
        if broker:
            tmp_celery = Celery("xagent", broker=broker, backend=broker)
            async_result = tmp_celery.send_task(
                "xagent.run_agent",
                kwargs={
                    "goal": body.goal,
                    "role": body.role,
                    "capabilities": body.capabilities,
                    "tenant_id": principal.tenant_id,
                    "user_id": principal.user_id,
                },
            )
            _task_tenants[async_result.id] = principal.tenant_id
            return {"task_id": async_result.id, "status": "pending", "backend": "celery"}
    except Exception:  # noqa: S110  Celery 发送失败降级进程内
        pass

    task_id = runner.submit(_run, kind="agent.run", tenant_id=principal.tenant_id)
    _task_tenants[task_id] = principal.tenant_id
    return {"task_id": task_id, "status": "pending", "backend": "inproc"}


@router.get("/{task_id}", summary="查询任务状态")
async def get_task(
    task_id: str,
    principal: Principal = Depends(require_permission("agent", "read")),
) -> dict:
    # 先查进程内 TaskRunner
    rec = get_task_runner().get(task_id, principal.tenant_id)
    if rec is not None:
        return {
            "task_id": rec.task_id,
            "kind": rec.kind,
            "status": rec.status.value,
            "result": rec.result,
            "error": rec.error,
            "created_at": rec.created_at,
            "finished_at": rec.finished_at,
        }
    # 进程内没有 -> 查 Celery backend（先校验租户归属）
    owner = _task_tenants.get(task_id)
    if owner is not None and owner != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在或无权访问")
    try:
        from celery import Celery

        from xagent.infra.settings import get_settings

        broker = get_settings().cache.redis_url
        if broker:
            tmp_celery = Celery("xagent", broker=broker, backend=broker)
            async_result = tmp_celery.AsyncResult(task_id)
            status_map = {
                "PENDING": "pending", "STARTED": "running", "SUCCESS": "succeeded",
                "FAILURE": "failed", "RETRY": "running",
            }
            task_status = status_map.get(async_result.state, async_result.state.lower())
            result = None
            error = None
            if async_result.successful():
                result = async_result.result
            elif async_result.failed():
                error = str(async_result.result)
            return {
                "task_id": task_id,
                "kind": "agent.run",
                "status": task_status,
                "result": result,
                "error": error,
                "created_at": None,
                "finished_at": None,
            }
    except Exception:  # noqa: S110  Celery 查询失败降级 404
        pass
    raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在或无权访问")


@router.get("", summary="列出当前租户任务")
async def list_tasks(
    principal: Principal = Depends(require_permission("agent", "read")),
) -> dict:
    recs = get_task_runner().list(principal.tenant_id)
    return {
        "tasks": [
            {
                "task_id": r.task_id,
                "kind": r.kind,
                "status": r.status.value,
                "created_at": r.created_at,
                "finished_at": r.finished_at,
            }
            for r in recs
        ]
    }
