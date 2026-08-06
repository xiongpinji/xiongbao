"""Durable scheduler 持久、租户隔离与原子 claim。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from xagent.domains.scheduled_jobs import (
    ScheduledJobCreate,
    claim_due_job,
    claim_due_retry,
    complete_scheduled_job_run,
    create_scheduled_job,
    get_scheduled_job,
    list_scheduled_job_runs,
    list_scheduled_jobs,
    recover_expired_job_runs,
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


async def test_expired_lease_recovers_and_retries_with_bounded_backoff(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    started = datetime.now(UTC)
    async with sessions() as session:
        await create_scheduled_job(
            session,
            ScheduledJobCreate(
                job_id="job-recover",
                tenant_id="tenant-recover",
                owner_id="owner-recover",
                name="recover me",
                goal="resume after restart",
                interval_seconds=3600,
                next_run=started,
                max_retries=2,
                retry_backoff_seconds=10,
            ),
        )
        first = await claim_due_job(
            session, now=started, lease_seconds=30, claim_token="worker-old"
        )
        await session.commit()
    assert first is not None

    recovery_time = started + timedelta(seconds=31)
    async with sessions() as session:
        recovered = await recover_expired_job_runs(session, now=recovery_time)
        await session.commit()
    assert recovered == 1

    async with sessions() as session:
        second = await claim_due_retry(
            session,
            now=recovery_time,
            lease_seconds=30,
            claim_token="worker-new",
        )
        await session.commit()
    assert second is not None
    assert second.run.attempt == 2

    failed_at = recovery_time + timedelta(seconds=1)
    async with sessions() as session:
        failed = await complete_scheduled_job_run(
            session,
            tenant_id="tenant-recover",
            run_id=second.run.run_id,
            succeeded=False,
            now=failed_at,
            error="provider unavailable",
        )
        await session.commit()
    assert failed.status == "retry_wait"
    assert failed.next_retry_at == failed_at + timedelta(seconds=20)

    async with sessions() as session:
        assert (
            await claim_due_retry(
                session,
                now=failed_at + timedelta(seconds=19),
                lease_seconds=30,
                claim_token="too-early",
            )
            is None
        )
        third = await claim_due_retry(
            session,
            now=failed_at + timedelta(seconds=20),
            lease_seconds=30,
            claim_token="worker-final",
        )
        await session.commit()
    assert third is not None
    assert third.run.attempt == 3

    async with sessions() as session:
        terminal = await complete_scheduled_job_run(
            session,
            tenant_id="tenant-recover",
            run_id=third.run.run_id,
            succeeded=False,
            now=failed_at + timedelta(seconds=21),
            error="still unavailable",
        )
        await session.commit()
        history = await list_scheduled_job_runs(
            session, "tenant-recover", "job-recover"
        )
    assert terminal.status == "failed"
    assert terminal.next_retry_at is None
    assert sorted(run.attempt for run in history) == [1, 2, 3]

    await engine.dispose()
