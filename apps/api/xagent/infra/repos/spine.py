from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.spine.models import DeliveryTask, Goal, Initiative
from xagent.infra.models.spine import DeliveryTaskORM, GoalORM, InitiativeORM


async def persist_goal(session: AsyncSession, goal: Goal) -> None:
    session.add(
        GoalORM(
            goal_id=goal.goal_id,
            tenant_id=goal.tenant_id,
            owner_id=goal.owner_id,
            title=goal.title,
            description=goal.description,
            phase=goal.phase.value,
            status=goal.status.value,
            metadata_json=json.dumps({}),
        )
    )


async def persist_initiatives(session: AsyncSession, initiatives: list[Initiative]) -> None:
    for item in initiatives:
        session.add(
            InitiativeORM(
                initiative_id=item.initiative_id,
                goal_id=item.goal_id,
                tenant_id=item.tenant_id,
                title=item.title,
                status=item.status,
                priority=item.priority,
            )
        )


async def persist_tasks(session: AsyncSession, tasks: list[DeliveryTask]) -> None:
    for task in tasks:
        session.add(
            DeliveryTaskORM(
                task_id=task.task_id,
                initiative_id=task.initiative_id,
                goal_id=task.goal_id,
                tenant_id=task.tenant_id,
                title=task.title,
                detail=task.detail,
                status=task.status,
                task_kind=task.task_kind,
                run_id=task.run_id,
                blocker_reason=task.blocker_reason,
            )
        )


async def load_goal_snapshot(session: AsyncSession, goal_id: str, tenant_id: str) -> dict | None:
    goal = await session.get(GoalORM, goal_id)
    if goal is None or goal.tenant_id != tenant_id:
        return None

    initiatives = (
        (
            await session.execute(
                select(InitiativeORM).where(
                    InitiativeORM.goal_id == goal_id,
                    InitiativeORM.tenant_id == tenant_id,
                )
            )
        )
        .scalars()
        .all()
    )
    tasks = (
        (
            await session.execute(
                select(DeliveryTaskORM).where(
                    DeliveryTaskORM.goal_id == goal_id,
                    DeliveryTaskORM.tenant_id == tenant_id,
                )
            )
        )
        .scalars()
        .all()
    )

    return {
        "goal": {
            "goal_id": goal.goal_id,
            "title": goal.title,
            "description": goal.description,
            "phase": goal.phase,
            "status": goal.status,
        },
        "initiatives": [
            {
                "initiative_id": item.initiative_id,
                "title": item.title,
                "status": item.status,
                "priority": item.priority,
            }
            for item in initiatives
        ],
        "tasks": [
            {
                "task_id": item.task_id,
                "initiative_id": item.initiative_id,
                "title": item.title,
                "detail": item.detail,
                "status": item.status,
                "task_kind": item.task_kind,
                "run_id": item.run_id,
                "blocker_reason": item.blocker_reason,
            }
            for item in tasks
        ],
    }
