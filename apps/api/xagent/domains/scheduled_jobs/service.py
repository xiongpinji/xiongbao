"""Durable scheduler 数据库仓储与 claim 原语。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import overload

from sqlalchemy import delete, exists, or_, select, update
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


async def set_scheduled_job_enabled(
    session: AsyncSession, tenant_id: str, job_id: str, enabled: bool
) -> ScheduledJobRecord | None:
    row = await session.scalar(
        select(ScheduledJobORM).where(
            ScheduledJobORM.tenant_id == tenant_id,
            ScheduledJobORM.job_id == job_id,
        )
    )
    if row is None:
        return None
    row.enabled = enabled
    await session.flush()
    return _job_record(row)


async def delete_scheduled_job(
    session: AsyncSession, tenant_id: str, job_id: str
) -> bool:
    result = await session.execute(
        delete(ScheduledJobORM)
        .where(
            ScheduledJobORM.tenant_id == tenant_id,
            ScheduledJobORM.job_id == job_id,
        )
        .returning(ScheduledJobORM.job_id)
    )
    return result.scalar_one_or_none() is not None


async def request_manual_job_run(
    session: AsyncSession, tenant_id: str, job_id: str, *, now: datetime
) -> ScheduledJobRunRecord | None:
    job = await session.scalar(
        select(ScheduledJobORM).where(
            ScheduledJobORM.tenant_id == tenant_id,
            ScheduledJobORM.job_id == job_id,
        )
    )
    if job is None:
        return None
    run = ScheduledJobRunORM(
        run_id=uuid.uuid4().hex,
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        scheduled_for=now,
        status="retry_wait",
        attempt=0,
        next_retry_at=now,
        error="manual run requested",
    )
    session.add(run)
    await session.flush()
    return _run_record(run)


async def claim_due_job(
    session: AsyncSession,
    *,
    now: datetime,
    lease_seconds: int,
    claim_token: str,
    job_id: str | None = None,
) -> ClaimedScheduledJob | None:
    """原子推进 next_run 后创建一个 run；一次只补最近的到期执行。"""
    candidate_query = (
        select(
            ScheduledJobORM.job_id,
            ScheduledJobORM.next_run,
            ScheduledJobORM.interval_seconds,
        )
        .where(ScheduledJobORM.enabled.is_(True), ScheduledJobORM.next_run <= now)
        .order_by(ScheduledJobORM.next_run)
        .limit(1)
    )
    if job_id is not None:
        candidate_query = candidate_query.where(ScheduledJobORM.job_id == job_id)
    candidate = (
        await session.execute(
            candidate_query
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


async def recover_expired_job_runs(session: AsyncSession, *, now: datetime) -> int:
    """将过期 running lease 标记为 interrupted，并立即进入重试队列。"""
    result = await session.execute(
        update(ScheduledJobRunORM)
        .where(
            ScheduledJobRunORM.status == "running",
            ScheduledJobRunORM.lease_expires_at.is_not(None),
            ScheduledJobRunORM.lease_expires_at < now,
        )
        .values(
            status="interrupted",
            error="worker lease expired",
            next_retry_at=now,
            lease_expires_at=None,
        )
        .returning(ScheduledJobRunORM.run_id)
    )
    return len(result.scalars().all())


async def claim_due_retry(
    session: AsyncSession,
    *,
    now: datetime,
    lease_seconds: int,
    claim_token: str,
    job_id: str | None = None,
) -> ClaimedScheduledJob | None:
    candidate_query = (
        select(
            ScheduledJobRunORM.run_id,
            ScheduledJobRunORM.job_id,
            ScheduledJobRunORM.scheduled_for,
            ScheduledJobRunORM.attempt,
        )
        .join(ScheduledJobORM, ScheduledJobORM.job_id == ScheduledJobRunORM.job_id)
        .where(
            ScheduledJobRunORM.status.in_(("interrupted", "retry_wait")),
            ScheduledJobRunORM.next_retry_at.is_not(None),
            ScheduledJobRunORM.next_retry_at <= now,
            or_(
                ScheduledJobORM.enabled.is_(True),
                ScheduledJobRunORM.attempt == 0,
            ),
            ScheduledJobRunORM.attempt <= ScheduledJobORM.max_retries,
        )
        .order_by(ScheduledJobRunORM.next_retry_at)
        .limit(1)
    )
    if job_id is not None:
        candidate_query = candidate_query.where(ScheduledJobRunORM.job_id == job_id)
    candidate = (
        await session.execute(
            candidate_query
        )
    ).first()
    if candidate is None:
        return None
    previous_run_id, job_id, scheduled_for, previous_attempt = candidate
    claimed = await session.execute(
        update(ScheduledJobRunORM)
        .where(
            ScheduledJobRunORM.run_id == previous_run_id,
            ScheduledJobRunORM.status.in_(("interrupted", "retry_wait")),
            ScheduledJobRunORM.next_retry_at <= now,
            exists().where(
                ScheduledJobORM.job_id == ScheduledJobRunORM.job_id,
                ScheduledJobRunORM.attempt <= ScheduledJobORM.max_retries,
                or_(
                    ScheduledJobORM.enabled.is_(True),
                    ScheduledJobRunORM.attempt == 0,
                ),
            ),
        )
        .values(status="retried", next_retry_at=None)
        .returning(ScheduledJobRunORM.run_id)
    )
    if claimed.scalar_one_or_none() is None:
        return None
    job = await session.get(ScheduledJobORM, job_id)
    if job is None:
        return None
    run = ScheduledJobRunORM(
        run_id=uuid.uuid4().hex,
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        scheduled_for=scheduled_for,
        status="running",
        attempt=previous_attempt + 1,
        claim_token=claim_token,
        claimed_at=now,
        lease_expires_at=now + timedelta(seconds=max(1, lease_seconds)),
        started_at=now,
    )
    session.add(run)
    await session.flush()
    return ClaimedScheduledJob(job=_job_record(job), run=_run_record(run))


async def get_due_retry_job_id(session: AsyncSession, *, now: datetime) -> str | None:
    return await session.scalar(
        select(ScheduledJobRunORM.job_id)
        .join(ScheduledJobORM, ScheduledJobORM.job_id == ScheduledJobRunORM.job_id)
        .where(
            ScheduledJobRunORM.status.in_(("interrupted", "retry_wait")),
            ScheduledJobRunORM.next_retry_at.is_not(None),
            ScheduledJobRunORM.next_retry_at <= now,
            or_(
                ScheduledJobORM.enabled.is_(True),
                ScheduledJobRunORM.attempt == 0,
            ),
            ScheduledJobRunORM.attempt <= ScheduledJobORM.max_retries,
        )
        .order_by(ScheduledJobRunORM.next_retry_at)
        .limit(1)
    )


async def get_due_job_id(session: AsyncSession, *, now: datetime) -> str | None:
    return await session.scalar(
        select(ScheduledJobORM.job_id)
        .where(ScheduledJobORM.enabled.is_(True), ScheduledJobORM.next_run <= now)
        .order_by(ScheduledJobORM.next_run)
        .limit(1)
    )


async def complete_scheduled_job_run(
    session: AsyncSession,
    *,
    tenant_id: str,
    run_id: str,
    succeeded: bool,
    now: datetime,
    result: str = "",
    error: str = "",
    agent_run_id: str = "",
) -> ScheduledJobRunRecord:
    row = await session.scalar(
        select(ScheduledJobRunORM).where(
            ScheduledJobRunORM.tenant_id == tenant_id,
            ScheduledJobRunORM.run_id == run_id,
        )
    )
    if row is None:
        raise LookupError(run_id)
    if row.status != "running":
        raise ValueError(f"调度运行 {run_id} 状态为 {row.status}，无法完成")
    job = await session.get(ScheduledJobORM, row.job_id)
    if job is None or job.tenant_id != tenant_id:
        raise LookupError(row.job_id)

    row.finished_at = now
    row.lease_expires_at = None
    row.agent_run_id = agent_run_id
    if succeeded:
        row.status = "succeeded"
        row.result = result[:4000]
        row.error = ""
        row.next_retry_at = None
    elif row.attempt <= job.max_retries:
        row.status = "retry_wait"
        row.error = error[:4000]
        delay = job.retry_backoff_seconds * (2 ** (row.attempt - 1))
        row.next_retry_at = now + timedelta(seconds=delay)
    else:
        row.status = "failed"
        row.error = error[:4000]
        row.next_retry_at = None
    await session.flush()
    return _run_record(row)


async def set_scheduled_job_run_notification(
    session: AsyncSession,
    *,
    tenant_id: str,
    run_id: str,
    status: str,
    error: str = "",
) -> ScheduledJobRunRecord:
    row = await session.scalar(
        select(ScheduledJobRunORM).where(
            ScheduledJobRunORM.tenant_id == tenant_id,
            ScheduledJobRunORM.run_id == run_id,
        )
    )
    if row is None:
        raise LookupError(run_id)
    if row.status not in {"succeeded", "failed"}:
        raise ValueError(f"调度运行 {run_id} 尚未终态，不能写通知结果")
    if status not in {"not_configured", "delivered", "failed"}:
        raise ValueError(f"无效通知状态: {status}")
    row.notification_status = status
    row.notification_error = error[:4000]
    await session.flush()
    return _run_record(row)
