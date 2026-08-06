"""Durable scheduler 持久、租户隔离与原子 claim。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from xagent.core.webhooks import WebhookDeliveryResult
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
from xagent.infra.db import Base, get_engine, get_sessionmaker
from xagent.infra.models.scheduled_job import ScheduledJobORM


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


async def test_scheduler_executes_claimed_run_and_persists_result(
    tmp_path: Path, monkeypatch
) -> None:
    from xagent.core.scheduler import Scheduler

    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        await create_scheduled_job(
            session,
            ScheduledJobCreate(
                job_id="job-execute",
                tenant_id="tenant-execute",
                owner_id="owner-execute",
                name="execute",
                goal="execute durable job",
                interval_seconds=300,
                next_run=now,
            ),
        )
        claimed = await claim_due_job(
            session, now=now, lease_seconds=60, claim_token="worker-execute"
        )
        await session.commit()
    assert claimed is not None

    class FakeRun:
        def to_dict(self):
            return {"run_id": "agent-run-1", "final_answer": "durable result"}

    async def fake_run_agent(*args, **kwargs):
        return FakeRun()

    monkeypatch.setattr("xagent.core.orchestration.run_agent", fake_run_agent)
    scheduler = Scheduler(storage_dir=tmp_path / "legacy-json")
    await scheduler._execute_durable_run(claimed)

    async with get_sessionmaker()() as session:
        history = await list_scheduled_job_runs(
            session, "tenant-execute", "job-execute"
        )
    assert history[0].status == "succeeded"
    assert history[0].agent_run_id == "agent-run-1"
    assert history[0].result == "durable result"
    assert history[0].notification_status == "not_configured"


async def test_scheduler_acquires_and_releases_redis_lease_around_db_claim(
    tmp_path: Path, monkeypatch
) -> None:
    from xagent.core.scheduler import Scheduler

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lease.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.now(UTC)
    async with sessions() as session:
        await create_scheduled_job(
            session,
            ScheduledJobCreate(
                job_id="job-redis-lease",
                tenant_id="tenant-redis-lease",
                owner_id="owner-redis-lease",
                name="redis lease",
                goal="execute under redis lease",
                interval_seconds=300,
                next_run=now,
            ),
        )
        await session.commit()

    class CapturingLock:
        def __init__(self):
            self.acquired = []
            self.released = []

        async def acquire(self, job_id, lease_seconds):
            self.acquired.append((job_id, lease_seconds))
            return True

        async def release(self, job_id):
            self.released.append(job_id)
            return True

    class FakeRun:
        def to_dict(self):
            return {"run_id": "agent-run-lease", "final_answer": "leased"}

    async def fake_run_agent(*args, **kwargs):
        return FakeRun()

    lock = CapturingLock()
    monkeypatch.setattr("xagent.infra.db.get_sessionmaker", lambda: sessions)
    monkeypatch.setattr("xagent.core.orchestration.run_agent", fake_run_agent)
    scheduler = Scheduler(
        storage_dir=tmp_path / "legacy-json-lease",
        job_lock=lock,  # type: ignore[arg-type]
    )

    claimed = await scheduler._claim_next_durable_run()
    assert claimed is not None
    assert lock.acquired == [("job-redis-lease", 360)]
    await scheduler._execute_durable_run(claimed)
    assert lock.released == ["job-redis-lease"]

    async with sessions() as session:
        history = await list_scheduled_job_runs(
            session, "tenant-redis-lease", "job-redis-lease"
        )
    assert history[0].status == "succeeded"
    await engine.dispose()


async def test_scheduler_does_not_create_run_when_redis_lease_is_denied(
    tmp_path: Path, monkeypatch
) -> None:
    from xagent.core.scheduler import Scheduler

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'denied.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    due = datetime.now(UTC)
    async with sessions() as session:
        await create_scheduled_job(
            session,
            ScheduledJobCreate(
                job_id="job-redis-denied",
                tenant_id="tenant-redis-denied",
                owner_id="owner-redis-denied",
                name="redis denied",
                goal="must not claim",
                interval_seconds=300,
                next_run=due,
            ),
        )
        await session.commit()

    class DeniedLock:
        async def acquire(self, job_id, lease_seconds):
            return False

        async def release(self, job_id):
            raise AssertionError("unowned lease must not be released")

    monkeypatch.setattr("xagent.infra.db.get_sessionmaker", lambda: sessions)
    scheduler = Scheduler(
        storage_dir=tmp_path / "legacy-json-denied",
        job_lock=DeniedLock(),  # type: ignore[arg-type]
    )
    assert await scheduler._claim_next_durable_run() is None

    async with sessions() as session:
        job = await get_scheduled_job(
            session, "tenant-redis-denied", "job-redis-denied"
        )
        history = await list_scheduled_job_runs(
            session, "tenant-redis-denied", "job-redis-denied"
        )
    assert job is not None
    assert job.next_run == due
    assert history == []
    await engine.dispose()


async def test_terminal_webhook_failure_is_persisted_without_changing_run_status(
    tmp_path: Path, monkeypatch
) -> None:
    from xagent.core.scheduler import Scheduler

    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        await create_scheduled_job(
            session,
            ScheduledJobCreate(
                job_id="job-webhook-failure",
                tenant_id="tenant-webhook-failure",
                owner_id="owner-webhook-failure",
                name="webhook failure",
                goal="finish despite notification failure",
                interval_seconds=300,
                next_run=now,
            ),
        )
        claimed = await claim_due_job(
            session, now=now, lease_seconds=60, claim_token="worker-webhook"
        )
        await session.commit()
    assert claimed is not None

    class FakeRun:
        def to_dict(self):
            return {"run_id": "agent-run-webhook", "final_answer": "completed"}

    class FailedWebhookManager:
        async def emit(self, tenant_id, event, payload):
            assert payload["agent_run_id"] == "agent-run-webhook"
            return WebhookDeliveryResult(
                target_count=1,
                delivered_count=0,
                errors=("hook-1: HTTP 503",),
            )

    async def fake_run_agent(*args, **kwargs):
        return FakeRun()

    monkeypatch.setattr("xagent.core.orchestration.run_agent", fake_run_agent)
    monkeypatch.setattr(
        "xagent.core.webhooks.get_webhook_manager",
        lambda: FailedWebhookManager(),
    )
    scheduler = Scheduler(storage_dir=tmp_path / "legacy-json")
    await scheduler._execute_durable_run(claimed)

    async with get_sessionmaker()() as session:
        history = await list_scheduled_job_runs(
            session, "tenant-webhook-failure", "job-webhook-failure"
        )
    assert history[0].status == "succeeded"
    assert history[0].notification_status == "failed"
    assert history[0].notification_error == "hook-1: HTTP 503"


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


async def test_paused_job_does_not_consume_due_retry(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'paused-retry.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    started = datetime.now(UTC)
    async with sessions() as session:
        await create_scheduled_job(
            session,
            ScheduledJobCreate(
                job_id="job-paused-retry",
                tenant_id="tenant-paused-retry",
                owner_id="owner-paused-retry",
                name="paused retry",
                goal="do not consume retry",
                interval_seconds=3600,
                next_run=started,
            ),
        )
        first = await claim_due_job(
            session, now=started, lease_seconds=30, claim_token="worker-first"
        )
        assert first is not None
        failed = await complete_scheduled_job_run(
            session,
            tenant_id="tenant-paused-retry",
            run_id=first.run.run_id,
            succeeded=False,
            now=started,
            error="retry later",
        )
        job = await session.get(ScheduledJobORM, "job-paused-retry")
        assert job is not None
        job.enabled = False
        await session.commit()

    async with sessions() as session:
        claimed = await claim_due_retry(
            session,
            now=failed.next_retry_at,
            lease_seconds=30,
            claim_token="worker-paused",
        )
        await session.commit()
    assert claimed is None

    async with sessions() as session:
        runs = await list_scheduled_job_runs(
            session, "tenant-paused-retry", "job-paused-retry"
        )
    assert len(runs) == 1
    assert runs[0].status == "retry_wait"
    assert runs[0].next_retry_at == failed.next_retry_at

    await engine.dispose()
