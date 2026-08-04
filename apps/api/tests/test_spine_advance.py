"""P4 自动推进循环测试（spine advance tick）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from xagent.core.spine.advance import (
    advance_goal,
    is_transient_blocker,
    parse_advance_config,
)
from xagent.core.spine.service import create_goal, decompose_goal
from xagent.infra.db import Base
from xagent.infra.models.spine import DeliveryTaskORM, GoalORM
from xagent.infra.repos.spine import persist_goal, persist_initiatives, persist_tasks


@pytest.fixture
async def db_session(tmp_path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/x.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def test_transient_blocker_classification() -> None:
    assert is_transient_blocker("LLM 调用超时（300s）")
    assert is_transient_blocker("HTTP 429 rate limit")
    assert is_transient_blocker("ConnectionError: econnreset")
    assert not is_transient_blocker("断言失败：结果不符合预期")
    assert not is_transient_blocker("")


def test_parse_advance_config() -> None:
    cfg = parse_advance_config({
        "auto_advance": True, "auto_execute": True, "advance_max_retries": 5,
    })
    assert cfg.enabled and cfg.auto_execute and cfg.max_retries == 5
    assert not parse_advance_config({}).enabled
    assert parse_advance_config({"auto_advance": True}).max_retries == 3


async def _seed_goal(session: AsyncSession, *, auto_advance: bool = True) -> str:
    goal = create_goal(tenant_id="t1", owner_id="u1", title="demo goal", description="d")
    initiatives, tasks = decompose_goal(goal)
    await persist_goal(session, goal)
    await session.flush()
    await persist_initiatives(session, initiatives)
    await persist_tasks(session, tasks)
    row = await session.get(GoalORM, goal.goal_id)
    row.metadata_json = json.dumps({"auto_advance": auto_advance})
    await session.commit()
    return goal.goal_id


async def test_tick_activates_pending_goal(db_session: AsyncSession) -> None:
    goal_id = await _seed_goal(db_session)
    goal = await db_session.get(GoalORM, goal_id)
    assert goal.status == "pending"
    result = await advance_goal(db_session, goal)
    await db_session.commit()
    assert goal.status == "active"
    assert any(a["kind"] == "goal_activated" for a in result["actions"])


async def test_tick_retries_transient_recovery_task(db_session: AsyncSession) -> None:
    goal_id = await _seed_goal(db_session)
    # 把一个任务打进 recovery（瞬态 blocker）
    from sqlalchemy import select as _select

    row = (await db_session.execute(
        _select(DeliveryTaskORM).where(DeliveryTaskORM.goal_id == goal_id)
    )).scalars().first()
    row.status = "recovery"
    row.blocker_reason = "LLM 调用超时（300s）"
    await db_session.commit()

    goal = await db_session.get(GoalORM, goal_id)
    result = await advance_goal(db_session, goal)
    await db_session.commit()

    assert row.status == "ready"
    assert row.blocker_reason == ""
    retried = [a for a in result["actions"] if a["kind"] == "task_retried"]
    assert retried and retried[0]["attempt"] == 1
    # 重试计数写入 goal metadata
    metadata = json.loads(goal.metadata_json)
    assert metadata["advance_retries"][row.task_id] == 1


async def test_tick_respects_retry_cap(db_session: AsyncSession) -> None:
    goal_id = await _seed_goal(db_session)
    from sqlalchemy import select as _select

    row = (await db_session.execute(
        _select(DeliveryTaskORM).where(DeliveryTaskORM.goal_id == goal_id)
    )).scalars().first()
    row.status = "recovery"
    row.blocker_reason = "timeout"
    goal = await db_session.get(GoalORM, goal_id)
    goal.metadata_json = json.dumps({
        "auto_advance": True,
        "advance_retries": {row.task_id: 3},  # 已达上限
    })
    await db_session.commit()

    result = await advance_goal(db_session, goal)
    await db_session.commit()
    assert row.status == "recovery"  # 不再重试
    assert any(a["kind"] == "task_needs_human" for a in result["actions"])


async def test_tick_skips_non_transient_blocker(db_session: AsyncSession) -> None:
    goal_id = await _seed_goal(db_session)
    from sqlalchemy import select as _select

    row = (await db_session.execute(
        _select(DeliveryTaskORM).where(DeliveryTaskORM.goal_id == goal_id)
    )).scalars().first()
    row.status = "recovery"
    row.blocker_reason = "断言失败：结果不符合预期"
    await db_session.commit()

    goal = await db_session.get(GoalORM, goal_id)
    await advance_goal(db_session, goal)
    await db_session.commit()
    assert row.status == "recovery"


async def test_tick_no_execute_without_auto_execute(db_session: AsyncSession) -> None:
    """auto_execute=false 时 ready 任务不会被起 run（不花 LLM 费用）。"""
    goal_id = await _seed_goal(db_session)
    goal = await db_session.get(GoalORM, goal_id)
    result = await advance_goal(db_session, goal)
    await db_session.commit()
    assert not any(a["kind"] == "task_executed" for a in result["actions"])
