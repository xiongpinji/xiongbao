"""可审查开发任务 API：租户隔离、显式确认与路径脱敏。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.orchestration.parallel import cancel_running_development_task
from xagent.domains.development_tasks import (
    DevelopmentTaskApplyError,
    DevelopmentTaskNotFoundError,
    DevelopmentTaskRecord,
    DevelopmentTaskStatus,
    DevelopmentTaskTransitionError,
    apply_development_task,
    approve_development_task,
    get_development_task,
    list_development_tasks,
    reject_development_task,
)
from xagent.domains.development_tasks.git_lifecycle import validate_record_paths
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session

router = APIRouter(prefix="/development-tasks", tags=["development-tasks"])

_PATCH_READABLE_STATUSES = frozenset(
    {
        DevelopmentTaskStatus.awaiting_review,
        DevelopmentTaskStatus.approved,
        DevelopmentTaskStatus.applied,
        DevelopmentTaskStatus.rejected,
        DevelopmentTaskStatus.conflict,
        DevelopmentTaskStatus.expired,
    }
)


class TaskConfirmation(BaseModel):
    confirm_task_id: str = Field(min_length=1)


def _load_json(value: str, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _public_task(record: DevelopmentTaskRecord) -> dict[str, Any]:
    """仅返回跨环境稳定字段，不暴露本机仓库、worktree 或补丁路径。"""
    return {
        "task_id": record.task_id,
        "parent_run_id": record.parent_run_id,
        "sub_run_id": record.sub_run_id,
        "owner_id": record.owner_id,
        "goal": record.goal,
        "status": record.status.value,
        "base_commit": record.base_commit,
        "target_branch": record.target_branch,
        "work_branch": record.work_branch,
        "result_commit": record.result_commit,
        "applied_commit": record.applied_commit,
        "diff_stat": record.diff_stat,
        "test_summary": _load_json(record.test_summary, {}),
        "conflict_files": _load_json(record.conflict_files, []),
        "error": record.error,
        "reviewed_by": record.reviewed_by,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "applied_at": record.applied_at.isoformat() if record.applied_at else None,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
    }


def _confirm(task_id: str, body: TaskConfirmation) -> None:
    if body.confirm_task_id != task_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "确认的任务 ID 与路径不一致")


async def _require_task(
    session: AsyncSession, tenant_id: str, task_id: str
) -> DevelopmentTaskRecord:
    record = await get_development_task(session, tenant_id, task_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "开发任务不存在")
    return record


def _record_action(
    principal: Principal, action: str, record: DevelopmentTaskRecord
) -> None:
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action=f"development_task.{action}",
        resource="development_task",
        detail={"task_id": record.task_id, "status": record.status.value},
    )


def _raise_domain_error(exc: Exception) -> None:
    if isinstance(exc, DevelopmentTaskNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "开发任务不存在") from exc
    if isinstance(
        exc, (DevelopmentTaskTransitionError, DevelopmentTaskApplyError, ValueError)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    raise exc


@router.get("")
async def read_development_tasks(
    task_status: DevelopmentTaskStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(require_permission("agent", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    records = await list_development_tasks(session, principal.tenant_id)
    if task_status is not None:
        records = [record for record in records if record.status == task_status]
    return {"items": [_public_task(record) for record in records[:limit]]}


@router.get("/{task_id}")
async def read_development_task(
    task_id: str,
    principal: Principal = Depends(require_permission("agent", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return _public_task(await _require_task(session, principal.tenant_id, task_id))


@router.get("/{task_id}/patch")
async def read_development_task_patch(
    task_id: str,
    principal: Principal = Depends(require_permission("agent", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    record = await _require_task(session, principal.tenant_id, task_id)
    if record.status not in _PATCH_READABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"开发任务当前状态不可读取补丁: {record.status.value}",
        )
    try:
        paths = validate_record_paths(
            Path(record.main_workspace),
            record.task_id,
            record.worktree_path,
            record.patch_path,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if not await asyncio.to_thread(paths.patch.is_file):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "开发任务补丁不存在")
    patch = await asyncio.to_thread(paths.patch.read_text, encoding="utf-8")
    return {"task_id": task_id, "patch": patch}


@router.post("/{task_id}/approve")
async def approve_task(
    task_id: str,
    body: TaskConfirmation,
    principal: Principal = Depends(require_permission("code_review", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _confirm(task_id, body)
    try:
        record = await approve_development_task(
            session,
            principal.tenant_id,
            task_id,
            reviewer_id=principal.user_id,
        )
    except Exception as exc:
        _raise_domain_error(exc)
    await session.commit()
    _record_action(principal, "approve", record)
    return _public_task(record)


@router.post("/{task_id}/reject")
async def reject_task(
    task_id: str,
    body: TaskConfirmation,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _confirm(task_id, body)
    try:
        record = await reject_development_task(
            session, principal.tenant_id, task_id, actor_id=principal.user_id
        )
    except Exception as exc:
        _raise_domain_error(exc)
    await session.commit()
    _record_action(principal, "reject", record)
    return _public_task(record)


@router.post("/{task_id}/apply")
async def apply_task(
    task_id: str,
    body: TaskConfirmation,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _confirm(task_id, body)
    try:
        record = await apply_development_task(
            session, principal.tenant_id, task_id, actor_id=principal.user_id
        )
    except Exception as exc:
        _raise_domain_error(exc)
    await session.commit()
    _record_action(principal, "apply", record)
    return _public_task(record)


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    body: TaskConfirmation,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _confirm(task_id, body)
    record = await _require_task(session, principal.tenant_id, task_id)
    if record.status != DevelopmentTaskStatus.running:
        raise HTTPException(status.HTTP_409_CONFLICT, "仅运行中的开发任务可取消")
    if not cancel_running_development_task(task_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "任务不在当前 API 进程中运行"
        )
    _record_action(principal, "cancel_requested", record)
    return {"task_id": task_id, "status": "cancellation_requested"}
