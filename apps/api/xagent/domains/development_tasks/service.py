"""开发任务仓储服务。"""

from __future__ import annotations

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
