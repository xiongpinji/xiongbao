from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.spine.models import DeliveryTask, Goal, GoalStatus, Initiative, SpinePhase
from xagent.infra.models.spine import DeliveryTaskORM, GoalORM, InitiativeORM


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _serialize_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat()


def _enum_storage_value(value: Enum | str) -> str:
    if isinstance(value, Enum):
        return value.value
    return value


def _safe_goal_phase(value: str) -> SpinePhase | str:
    try:
        return SpinePhase(value)
    except ValueError:
        return value


def _safe_goal_status(value: str) -> GoalStatus | str:
    try:
        return GoalStatus(value)
    except ValueError:
        return value


def _goal_from_orm(row: GoalORM) -> Goal:
    return Goal(
        goal_id=row.goal_id,
        tenant_id=row.tenant_id,
        owner_id=row.owner_id,
        title=row.title,
        description=row.description,
        phase=_safe_goal_phase(row.phase),
        status=_safe_goal_status(row.status),
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
            phase=_enum_storage_value(goal.phase),
            status=_enum_storage_value(goal.status),
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

    initiative_rows = (
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
    initiative_views = [_initiative_from_orm(item).to_dict() for item in initiative_rows]
    initiative_order = {
        item.initiative_id: (index, item.position, item.initiative_id)
        for index, item in enumerate(initiative_rows)
    }

    task_rows = (
        (
            await session.execute(
                select(DeliveryTaskORM)
                .where(
                    DeliveryTaskORM.goal_id == goal_id,
                    DeliveryTaskORM.tenant_id == tenant_id,
                )
            )
        )
        .scalars()
        .all()
    )

    def _task_sort_key(row: DeliveryTaskORM) -> tuple[int, int, str, int, str]:
        parent = initiative_order.get(row.initiative_id)
        if parent is None:
            return (1, row.position, row.initiative_id, row.position, row.task_id)
        _index, initiative_position, initiative_id = parent
        return (0, initiative_position, initiative_id, row.position, row.task_id)

    task_views: list[dict] = []
    for row in sorted(task_rows, key=_task_sort_key):
        task_view = _task_from_orm(row).to_dict()
        task_view["orphaned"] = row.initiative_id not in initiative_order
        task_views.append(task_view)

    return {
        "goal": _goal_from_orm(goal).to_dict(),
        "initiatives": initiative_views,
        "tasks": task_views,
    }
