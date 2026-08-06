"""Durable scheduler 持久、租户隔离与原子 claim。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from xagent.domains.scheduled_jobs import (
    ScheduledJobCreate,
    claim_due_job,
    create_scheduled_job,
    get_scheduled_job,
    list_scheduled_job_runs,
    list_scheduled_jobs,
)
from xagent.infra.db import Base


async def test_job_persists_is_tenant_isolated_and_claims_once(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scheduler.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    due = datetime.now(UTC) - timedelta(minutes=10)
    async with sessions() as session:
        created = await create_scheduled_job(
            session,
            ScheduledJobCreate(
                job_id="job-durable-1",
                tenant_id="tenant-a",
                owner_id="owner-a",
                name="nightly audit",
                goal="run release audit",
                interval_seconds=300,
                next_run=due,
            ),
        )
        assert created.max_retries == 3
        await session.commit()

    async with sessions() as session:
        assert await get_scheduled_job(session, "tenant-b", "job-durable-1") is None
        assert [job.job_id for job in await list_scheduled_jobs(session, "tenant-a")] == [
            "job-durable-1"
        ]

    claimed_at = datetime.now(UTC)
    async with sessions() as session:
        first = await claim_due_job(
            session,
            now=claimed_at,
            lease_seconds=120,
            claim_token="worker-a",
        )
        await session.commit()
    async with sessions() as session:
        second = await claim_due_job(
            session,
            now=claimed_at,
            lease_seconds=120,
            claim_token="worker-b",
        )
        await session.commit()

    assert first is not None
    assert first.job.job_id == "job-durable-1"
    assert first.run.status == "running"
    assert first.run.attempt == 1
    assert first.run.scheduled_for == due
    assert second is None

    async with sessions() as session:
        persisted = await get_scheduled_job(session, "tenant-a", "job-durable-1")
        runs = await list_scheduled_job_runs(session, "tenant-a", "job-durable-1")
    assert persisted is not None
    assert persisted.next_run == claimed_at + timedelta(seconds=300)
    assert [run.run_id for run in runs] == [first.run.run_id]

    await engine.dispose()
