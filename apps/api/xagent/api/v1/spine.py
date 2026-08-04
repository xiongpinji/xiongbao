from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.spine.service import create_goal, decompose_goal
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session
from xagent.infra.repos.spine import (
    load_goal_snapshot,
    persist_goal,
    persist_initiatives,
    persist_tasks,
)

router = APIRouter(prefix="/spine", tags=["spine"])

TASKBOARD_COLUMNS = (
    "ready",
    "in_progress",
    "blocked",
    "review",
    "release_ready",
    "deploying",
    "verifying",
    "delivered",
    "recovery",
)


class GoalCreateIn(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(default="")


@router.post("/goals", summary="创建 delivery goal")
async def create_delivery_goal(
    body: GoalCreateIn,
    principal: Principal = Depends(require_permission("spine", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    goal = create_goal(
        tenant_id=principal.tenant_id,
        owner_id=principal.user_id,
        title=body.title,
        description=body.description,
    )
    initiatives, tasks = decompose_goal(goal)

    await persist_goal(session, goal)
    await session.flush()
    await persist_initiatives(session, initiatives)
    await session.flush()
    await persist_tasks(session, tasks)
    await session.commit()

    return {
        "goal": goal.to_dict(),
        "initiatives": [item.to_dict() for item in initiatives],
        "tasks": [item.to_dict() for item in tasks],
    }


@router.get("/goals/{goal_id}/board", summary="获取 goal taskboard 快照")
async def get_goal_board(
    goal_id: str,
    principal: Principal = Depends(require_permission("spine", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    snapshot = await load_goal_snapshot(session, goal_id, principal.tenant_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目标不存在或无权访问")

    columns: dict[str, list[dict]] = {column: [] for column in TASKBOARD_COLUMNS}
    unknown_status_tasks: list[dict] = []
    for task in snapshot["tasks"]:
        task_status = str(task["status"])
        if task_status in columns:
            columns[task_status].append(task)
        else:
            unknown_status_tasks.append(task)

    return {
        "goal": snapshot["goal"],
        "initiatives": snapshot["initiatives"],
        "columns": columns,
        "unknown_status_tasks": unknown_status_tasks,
    }


class AutoAdvanceIn(BaseModel):
    enabled: bool = Field(..., description="是否开启自动推进 tick")
    auto_execute: bool = Field(default=False, description="是否允许 tick 自动起 run（花 LLM 费用）")
    max_retries: int = Field(default=3, ge=0, le=10, description="recovery 瞬态失败自动重试上限")


@router.post("/goals/{goal_id}/auto-advance", summary="开关 goal 自动推进（P4）")
async def set_auto_advance(
    goal_id: str,
    body: AutoAdvanceIn,
    principal: Principal = Depends(require_permission("spine", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from xagent.core.spine.advance import DEFAULT_MAX_RETRIES
    from xagent.infra.models.spine import GoalORM

    goal = await session.get(GoalORM, goal_id)
    if goal is None or goal.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目标不存在或无权访问")

    import json as _json

    try:
        metadata = _json.loads(goal.metadata_json or "{}")
        if not isinstance(metadata, dict):
            metadata = {}
    except _json.JSONDecodeError:
        metadata = {}
    metadata["auto_advance"] = body.enabled
    metadata["auto_execute"] = body.auto_execute
    if body.max_retries != DEFAULT_MAX_RETRIES:
        metadata["advance_max_retries"] = body.max_retries
    else:
        metadata.pop("advance_max_retries", None)
    goal.metadata_json = _json.dumps(metadata, ensure_ascii=False)
    # 开启即激活（pending → active）；关闭不改 status
    if body.enabled and goal.status == "pending":
        goal.status = "active"
    await session.commit()
    return {
        "goal_id": goal_id,
        "auto_advance": body.enabled,
        "auto_execute": body.auto_execute,
        "max_retries": body.max_retries,
        "status": goal.status,
    }
