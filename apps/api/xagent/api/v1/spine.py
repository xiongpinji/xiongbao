from __future__ import annotations

from collections import defaultdict

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


class GoalCreateIn(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(default="")


@router.post("/goals", summary="创建 delivery goal")
async def create_delivery_goal(
    body: GoalCreateIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
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
    principal: Principal = Depends(require_permission("agent", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    snapshot = await load_goal_snapshot(session, goal_id, principal.tenant_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目标不存在或无权访问")

    columns: defaultdict[str, list[dict]] = defaultdict(list)
    for task in snapshot["tasks"]:
        columns[str(task["status"])].append(task)

    return {
        "goal": snapshot["goal"],
        "initiatives": snapshot["initiatives"],
        "columns": dict(columns),
    }
