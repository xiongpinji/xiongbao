"""Durable scheduler 领域数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ScheduledJobCreate:
    job_id: str
    tenant_id: str
    owner_id: str
    name: str
    goal: str
    interval_seconds: int
    next_run: datetime
    role: str = ""
    cron_expr: str = ""
    enabled: bool = True
    max_retries: int = 3
    retry_backoff_seconds: int = 60


@dataclass(frozen=True)
class ScheduledJobRecord:
    job_id: str
    tenant_id: str
    owner_id: str
    name: str
    goal: str
    role: str
    cron_expr: str
    interval_seconds: int
    enabled: bool
    max_retries: int
    retry_backoff_seconds: int
    last_run: datetime | None
    next_run: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ScheduledJobRunRecord:
    run_id: str
    job_id: str
    tenant_id: str
    scheduled_for: datetime
    status: str
    attempt: int
    claim_token: str
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    agent_run_id: str
    result: str
    error: str
    next_retry_at: datetime | None
    notification_status: str
    notification_error: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ClaimedScheduledJob:
    job: ScheduledJobRecord
    run: ScheduledJobRunRecord
