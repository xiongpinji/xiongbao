"""开发任务仓储服务。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.domains.development_tasks.models import (
    DevelopmentTaskCreate,
    DevelopmentTaskRecord,
    DevelopmentTaskStatus,
)
from xagent.infra.models.development_task import DevelopmentTaskORM

_MUTABLE_FIELDS = {
    "status",
    "result_commit",
    "applied_commit",
    "diff_stat",
    "test_summary",
    "conflict_files",
    "error",
    "reviewed_by",
    "reviewed_at",
    "applied_at",
    "expires_at",
    "worktree_path",
}


class DevelopmentTaskNotFoundError(LookupError):
    pass


class DevelopmentTaskTransitionError(ValueError):
    pass


class DevelopmentTaskApplyError(RuntimeError):
    pass


def _to_record(row: DevelopmentTaskORM) -> DevelopmentTaskRecord:
    return DevelopmentTaskRecord(
        task_id=row.task_id,
        parent_run_id=row.parent_run_id,
        sub_run_id=row.sub_run_id,
        tenant_id=row.tenant_id,
        owner_id=row.owner_id,
        goal=row.goal,
        status=DevelopmentTaskStatus(row.status),
        main_workspace=row.main_workspace,
        base_commit=row.base_commit,
        target_branch=row.target_branch,
        work_branch=row.work_branch,
        worktree_path=row.worktree_path,
        result_commit=row.result_commit,
        applied_commit=row.applied_commit,
        diff_stat=row.diff_stat,
        patch_path=row.patch_path,
        test_summary=row.test_summary,
        conflict_files=row.conflict_files,
        error=row.error,
        reviewed_by=row.reviewed_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        reviewed_at=row.reviewed_at,
        applied_at=row.applied_at,
        expires_at=row.expires_at,
    )


async def create_development_task(
    session: AsyncSession, data: DevelopmentTaskCreate
) -> DevelopmentTaskRecord:
    row = DevelopmentTaskORM(
        task_id=data.task_id,
        parent_run_id=data.parent_run_id,
        sub_run_id=data.sub_run_id,
        tenant_id=data.tenant_id,
        owner_id=data.owner_id,
        goal=data.goal,
        status=data.status.value,
        main_workspace=data.main_workspace,
        base_commit=data.base_commit,
        target_branch=data.target_branch,
        work_branch=data.work_branch,
        worktree_path=data.worktree_path,
        patch_path=data.patch_path,
        expires_at=data.expires_at,
    )
    session.add(row)
    await session.flush()
    return _to_record(row)


async def get_development_task(
    session: AsyncSession, tenant_id: str, task_id: str
) -> DevelopmentTaskRecord | None:
    row = await session.scalar(
        select(DevelopmentTaskORM).where(
            DevelopmentTaskORM.tenant_id == tenant_id,
            DevelopmentTaskORM.task_id == task_id,
        )
    )
    return _to_record(row) if row is not None else None


async def list_development_tasks(
    session: AsyncSession, tenant_id: str
) -> list[DevelopmentTaskRecord]:
    rows = await session.scalars(
        select(DevelopmentTaskORM)
        .where(DevelopmentTaskORM.tenant_id == tenant_id)
        .order_by(DevelopmentTaskORM.created_at.desc())
    )
    return [_to_record(row) for row in rows]


async def update_development_task(
    session: AsyncSession,
    tenant_id: str,
    task_id: str,
    **changes: Any,
) -> DevelopmentTaskRecord | None:
    unknown = set(changes) - _MUTABLE_FIELDS
    if unknown:
        raise ValueError(f"不可更新开发任务字段: {', '.join(sorted(unknown))}")
    row = await session.scalar(
        select(DevelopmentTaskORM).where(
            DevelopmentTaskORM.tenant_id == tenant_id,
            DevelopmentTaskORM.task_id == task_id,
        )
    )
    if row is None:
        return None
    for name, value in changes.items():
        if name == "status" and isinstance(value, DevelopmentTaskStatus):
            value = value.value
        setattr(row, name, value)
    await session.flush()
    return _to_record(row)


async def _require_task(
    session: AsyncSession, tenant_id: str, task_id: str
) -> DevelopmentTaskRecord:
    record = await get_development_task(session, tenant_id, task_id)
    if record is None:
        raise DevelopmentTaskNotFoundError(task_id)
    return record


def _require_status(
    record: DevelopmentTaskRecord, *allowed: DevelopmentTaskStatus
) -> None:
    if record.status not in allowed:
        expected = ", ".join(status.value for status in allowed)
        raise DevelopmentTaskTransitionError(
            f"任务 {record.task_id} 状态为 {record.status.value}，要求 {expected}"
        )


async def approve_development_task(
    session: AsyncSession,
    tenant_id: str,
    task_id: str,
    *,
    reviewer_id: str,
) -> DevelopmentTaskRecord:
    record = await _require_task(session, tenant_id, task_id)
    _require_status(record, DevelopmentTaskStatus.awaiting_review)
    updated = await update_development_task(
        session,
        tenant_id,
        task_id,
        status=DevelopmentTaskStatus.approved,
        reviewed_by=reviewer_id,
        reviewed_at=datetime.now(UTC),
        error="",
    )
    assert updated is not None
    return updated


async def reject_development_task(
    session: AsyncSession,
    tenant_id: str,
    task_id: str,
    *,
    actor_id: str,
) -> DevelopmentTaskRecord:
    record = await _require_task(session, tenant_id, task_id)
    _require_status(
        record,
        DevelopmentTaskStatus.awaiting_review,
        DevelopmentTaskStatus.approved,
        DevelopmentTaskStatus.conflict,
    )
    from xagent.domains.development_tasks.git_lifecycle import (
        cleanup_task_worktree,
        validate_record_paths,
    )

    repo_root = Path(record.main_workspace)
    paths = validate_record_paths(
        repo_root, record.task_id, record.worktree_path, record.patch_path
    )
    await cleanup_task_worktree(repo_root, paths, record.work_branch)
    updated = await update_development_task(
        session,
        tenant_id,
        task_id,
        status=DevelopmentTaskStatus.rejected,
        reviewed_by=actor_id,
        reviewed_at=datetime.now(UTC),
        error="",
    )
    assert updated is not None
    return updated


async def expire_development_task(
    session: AsyncSession,
    tenant_id: str,
    task_id: str,
) -> DevelopmentTaskRecord:
    record = await _require_task(session, tenant_id, task_id)
    _require_status(
        record,
        DevelopmentTaskStatus.awaiting_review,
        DevelopmentTaskStatus.approved,
        DevelopmentTaskStatus.conflict,
    )
    from xagent.domains.development_tasks.git_lifecycle import (
        cleanup_task_worktree,
        validate_record_paths,
    )

    repo_root = Path(record.main_workspace)
    paths = validate_record_paths(
        repo_root, record.task_id, record.worktree_path, record.patch_path
    )
    await cleanup_task_worktree(repo_root, paths, record.work_branch)
    updated = await update_development_task(
        session,
        tenant_id,
        task_id,
        status=DevelopmentTaskStatus.expired,
        error="审查期限已过期",
    )
    assert updated is not None
    return updated


async def apply_development_task(
    session: AsyncSession,
    tenant_id: str,
    task_id: str,
    *,
    actor_id: str,
) -> DevelopmentTaskRecord:
    record = await _require_task(session, tenant_id, task_id)
    _require_status(record, DevelopmentTaskStatus.approved)
    from xagent.domains.development_tasks.git_lifecycle import (
        apply_result_commit,
        cleanup_task_worktree,
        validate_record_paths,
    )

    repo_root = Path(record.main_workspace)
    paths = validate_record_paths(
        repo_root, record.task_id, record.worktree_path, record.patch_path
    )
    try:
        result = await apply_result_commit(
            repo_root, record.target_branch, record.result_commit
        )
    except RuntimeError as exc:
        raise DevelopmentTaskApplyError(str(exc)) from exc
    if not result.succeeded:
        updated = await update_development_task(
            session,
            tenant_id,
            task_id,
            status=DevelopmentTaskStatus.conflict,
            conflict_files=json.dumps(list(result.conflict_files), ensure_ascii=False),
            error=result.error,
        )
        assert updated is not None
        return updated

    await cleanup_task_worktree(repo_root, paths, record.work_branch)
    updated = await update_development_task(
        session,
        tenant_id,
        task_id,
        status=DevelopmentTaskStatus.applied,
        applied_commit=result.applied_commit,
        applied_at=datetime.now(UTC),
        reviewed_by=record.reviewed_by or actor_id,
        conflict_files="[]",
        error="",
    )
    assert updated is not None
    return updated
