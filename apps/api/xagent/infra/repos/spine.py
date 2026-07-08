from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.spine.models import DeliveryTask, Goal, GoalStatus, Initiative, SpinePhase
from xagent.infra.models.spine import DeliveryTaskORM, GoalORM, InitiativeORM


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _serialize_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _goal_from_orm(row: GoalORM) -> Goal:
    return Goal(
        goal_id=row.goal_id,
        tenant_id=row.tenant_id,
        owner_id=row.owner_id,
        title=row.title,
        description=row.description,
        phase=SpinePhase(row.phase),
        status=GoalStatus(row.status),
        created_at=_serialize_timestamp(row.created_at),
        updated_at=_serialize_timestamp(row.updated_at),
    )


def _initiative_from_orm(row: InitiativeORM) -> Initiative:
    return Initiative(
        initiative_id=row.initiative_id,
        goal_id=row.goal_id,
        tenant_id=row.tenant_id,
        title=row.title,
        status=row.status,
        priority=row.priority,
        position=row.position,
        created_at=_serialize_timestamp(row.created_at),
        updated_at=_serialize_timestamp(row.updated_at),
    )


def _task_from_orm(row: DeliveryTaskORM) -> DeliveryTask:
    return DeliveryTask(
        task_id=row.task_id,
        initiative_id=row.initiative_id,
        goal_id=row.goal_id,
        tenant_id=row.tenant_id,
        title=row.title,
        detail=row.detail,
        status=row.status,
        task_kind=row.task_kind,
        run_id=row.run_id,
        blocker_reason=row.blocker_reason,
        position=row.position,
        created_at=_serialize_timestamp(row.created_at),
        updated_at=_serialize_timestamp(row.updated_at),
    )


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
            created_at=_parse_timestamp(goal.created_at),
            updated_at=_parse_timestamp(goal.updated_at),
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
                position=item.position,
                created_at=_parse_timestamp(item.created_at),
                updated_at=_parse_timestamp(item.updated_at),
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
                position=task.position,
                created_at=_parse_timestamp(task.created_at),
                updated_at=_parse_timestamp(task.updated_at),
            )
        )


async def load_goal_snapshot(session: AsyncSession, goal_id: str, tenant_id: str) -> dict | None:
    goal = await session.get(GoalORM, goal_id)
    if goal is None or goal.tenant_id != tenant_id:
        return None

    initiatives = (
        (
            await session.execute(
                select(InitiativeORM)
                .where(
                    InitiativeORM.goal_id == goal_id,
                    InitiativeORM.tenant_id == tenant_id,
                )
                .order_by(InitiativeORM.position.asc(), InitiativeORM.initiative_id.asc())
            )
        )
        .scalars()
        .all()
    )
    tasks = (
        (
            await session.execute(
                select(DeliveryTaskORM)
                .where(
                    DeliveryTaskORM.goal_id == goal_id,
                    DeliveryTaskORM.tenant_id == tenant_id,
                )
                .order_by(DeliveryTaskORM.position.asc(), DeliveryTaskORM.task_id.asc())
            )
        )
        .scalars()
        .all()
    )

    return {
        "goal": _goal_from_orm(goal).to_dict(),
        "initiatives": [_initiative_from_orm(item).to_dict() for item in initiatives],
        "tasks": [_task_from_orm(item).to_dict() for item in tasks],
    }
