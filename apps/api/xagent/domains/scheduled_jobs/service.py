"""Durable scheduler 数据库仓储与 claim 原语。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import overload

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.domains.scheduled_jobs.models import (
    ClaimedScheduledJob,
    ScheduledJobCreate,
    ScheduledJobRecord,
    ScheduledJobRunRecord,
)
from xagent.infra.models.scheduled_job import ScheduledJobORM, ScheduledJobRunORM


@overload
def _as_utc(value: datetime) -> datetime: ...


@overload
def _as_utc(value: None) -> None: ...


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _job_record(row: ScheduledJobORM) -> ScheduledJobRecord:
    return ScheduledJobRecord(
        job_id=row.job_id,
        tenant_id=row.tenant_id,
        owner_id=row.owner_id,
        name=row.name,
        goal=row.goal,
        role=row.role,
        cron_expr=row.cron_expr,
        interval_seconds=row.interval_seconds,
        enabled=row.enabled,
        max_retries=row.max_retries,
        retry_backoff_seconds=row.retry_backoff_seconds,
        last_run=_as_utc(row.last_run),
        next_run=_as_utc(row.next_run),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


def _run_record(row: ScheduledJobRunORM) -> ScheduledJobRunRecord:
    return ScheduledJobRunRecord(
        run_id=row.run_id,
        job_id=row.job_id,
        tenant_id=row.tenant_id,
        scheduled_for=_as_utc(row.scheduled_for),
        status=row.status,
        attempt=row.attempt,
        claim_token=row.claim_token,
        claimed_at=_as_utc(row.claimed_at),
        lease_expires_at=_as_utc(row.lease_expires_at),
        started_at=_as_utc(row.started_at),
        finished_at=_as_utc(row.finished_at),
        agent_run_id=row.agent_run_id,
        result=row.result,
        error=row.error,
        next_retry_at=_as_utc(row.next_retry_at),
        notification_status=row.notification_status,
        notification_error=row.notification_error,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


async def create_scheduled_job(
    session: AsyncSession, data: ScheduledJobCreate
) -> ScheduledJobRecord:
    if data.interval_seconds < 1:
        raise ValueError("interval_seconds 必须大于 0")
    if data.max_retries < 0 or data.max_retries > 10:
        raise ValueError("max_retries 必须在 0..10")
    row = ScheduledJobORM(**data.__dict__)
    session.add(row)
    await session.flush()
    return _job_record(row)


async def get_scheduled_job(
    session: AsyncSession, tenant_id: str, job_id: str
) -> ScheduledJobRecord | None:
    row = await session.scalar(
        select(ScheduledJobORM).where(
            ScheduledJobORM.tenant_id == tenant_id,
            ScheduledJobORM.job_id == job_id,
        )
    )
    return _job_record(row) if row is not None else None


async def list_scheduled_jobs(session: AsyncSession, tenant_id: str) -> list[ScheduledJobRecord]:
    rows = await session.scalars(
        select(ScheduledJobORM)
        .where(ScheduledJobORM.tenant_id == tenant_id)
        .order_by(ScheduledJobORM.next_run)
    )
    return [_job_record(row) for row in rows]


async def list_scheduled_job_runs(
    session: AsyncSession, tenant_id: str, job_id: str | None = None
) -> list[ScheduledJobRunRecord]:
    query = select(ScheduledJobRunORM).where(ScheduledJobRunORM.tenant_id == tenant_id)
    if job_id is not None:
        query = query.where(ScheduledJobRunORM.job_id == job_id)
    rows = await session.scalars(query.order_by(ScheduledJobRunORM.created_at.desc()))
    return [_run_record(row) for row in rows]


async def claim_due_job(
    session: AsyncSession,
    *,
    now: datetime,
    lease_seconds: int,
    claim_token: str,
) -> ClaimedScheduledJob | None:
    """原子推进 next_run 后创建一个 run；一次只补最近的到期执行。"""
    candidate = (
        await session.execute(
            select(
                ScheduledJobORM.job_id,
                ScheduledJobORM.next_run,
                ScheduledJobORM.interval_seconds,
            )
            .where(ScheduledJobORM.enabled.is_(True), ScheduledJobORM.next_run <= now)
            .order_by(ScheduledJobORM.next_run)
            .limit(1)
        )
    ).first()
    if candidate is None:
        return None
    job_id, scheduled_for, interval_seconds = candidate
    result = await session.execute(
        update(ScheduledJobORM)
        .where(
            ScheduledJobORM.job_id == job_id,
            ScheduledJobORM.enabled.is_(True),
            ScheduledJobORM.next_run <= now,
        )
        .values(last_run=scheduled_for, next_run=now + timedelta(seconds=interval_seconds))
        .returning(ScheduledJobORM.job_id)
    )
    claimed_job_id = result.scalar_one_or_none()
    if claimed_job_id is None:
        return None
    job = await session.get(ScheduledJobORM, claimed_job_id)
    assert job is not None
    run = ScheduledJobRunORM(
        run_id=uuid.uuid4().hex,
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        scheduled_for=scheduled_for,
        status="running",
        attempt=1,
        claim_token=claim_token,
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=max(1, lease_seconds)),
        started_at=now,
    )
    session.add(run)
    await session.flush()
    return ClaimedScheduledJob(job=_job_record(job), run=_run_record(run))
