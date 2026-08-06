"""租户 checkpoint 时间线、恢复与受控 Git 回滚 API。"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.orchestration import run_agent
from xagent.domains.checkpoints import (
    CheckpointRecord,
    create_resume_checkpoint,
    get_checkpoint,
    list_checkpoints,
    redact_checkpoint_text,
    rollback_checkpoint,
    update_checkpoint_status,
)
from xagent.domains.checkpoints.rollback import CheckpointRollbackError
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session, get_sessionmaker
from xagent.infra.logging import get_logger
from xagent.worker.celery_app import persist_agent_task_record

router = APIRouter(prefix="/checkpoints", tags=["checkpoints"])
logger = get_logger("xagent.api.checkpoints")


class ResumeCheckpointIn(BaseModel):
    confirm_checkpoint_id: str = Field(..., min_length=1)


class RollbackCheckpointIn(BaseModel):
    confirm_checkpoint_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    source: Literal["commit", "patch"]


def _view(record: CheckpointRecord, *, detail: bool) -> dict[str, Any]:
    value = asdict(record)
    if not detail:
        value.pop("messages", None)
    return value


async def _mark_resume(
    record: CheckpointRecord, *, status_value: str, error: str = ""
) -> None:
    async with get_sessionmaker()() as session:
        await update_checkpoint_status(
            session,
            record.tenant_id,
            record.checkpoint_id,
            status=status_value,
            error=error,
        )
        await session.commit()


async def _run_resumed_checkpoint(
    record: CheckpointRecord, principal: Principal
) -> None:
    started_at = datetime.now(UTC)
    await _mark_resume(record, status_value="running")
    try:
        async with get_sessionmaker()() as tool_session:
            result = await run_agent(
                record.goal,
                principal=principal,
                capabilities=None,
                session=tool_session,
                run_id=record.run_id,
                conversation_id=record.conversation_id,
                resume_messages=record.messages,
                resume_step=record.step,
                resume_changed_files=record.changed_files,
                resume_from_checkpoint_id=record.parent_checkpoint_id,
            )
        result_payload = result.to_dict()
        delivery = {
            "status": "ready",
            "channel": "task_runtime",
            "kind": "checkpoint.resume",
            "summary": f"已从 checkpoint 恢复并完成 {result.steps} 个步骤。",
            "replay": {
                "mode": "task_detail",
                "run_id": result.run_id,
                "task_id": result.run_id,
                "api_path": f"/api/v1/runs/{result.run_id}",
                "console_path": f"/runs/{result.run_id}",
            },
            "risks": [],
        }
        await persist_agent_task_record(
            task_id=result.run_id,
            run_id=result.run_id,
            tenant_id=principal.tenant_id,
            owner_id=principal.user_id,
            kind="checkpoint.resume",
            backend="checkpoint",
            status="succeeded",
            input_payload={
                "checkpoint_id": record.parent_checkpoint_id,
                "conversation_id": record.conversation_id,
            },
            result_payload=result_payload,
            delivery_summary=delivery,
            lineage_summary={
                "parent_checkpoint_id": record.parent_checkpoint_id,
                "checkpoint_id": record.checkpoint_id,
            },
            preview_summary={"final_answer": result.final_answer[:160]},
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        await _mark_resume(record, status_value="completed")
    except Exception as exc:
        safe_error = redact_checkpoint_text(str(exc))[:1000]
        try:
            await persist_agent_task_record(
                task_id=record.run_id,
                run_id=record.run_id,
                tenant_id=principal.tenant_id,
                owner_id=principal.user_id,
                kind="checkpoint.resume",
                backend="checkpoint",
                status="failed",
                input_payload={
                    "checkpoint_id": record.parent_checkpoint_id,
                    "conversation_id": record.conversation_id,
                },
                result_payload={"run_id": record.run_id, "status": "failed"},
                error=safe_error,
                lineage_summary={
                    "parent_checkpoint_id": record.parent_checkpoint_id,
                    "checkpoint_id": record.checkpoint_id,
                },
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        finally:
            await _mark_resume(record, status_value="failed", error=safe_error)
        logger.warning(
            "checkpoint_resume_failed",
            checkpoint_id=record.checkpoint_id,
            run_id=record.run_id,
            error=safe_error,
        )


@router.get("", summary="列出 checkpoint 时间线")
async def list_checkpoint_timeline(
    conversation_id: str = Query(default=""),
    run_id: str = Query(default=""),
    principal: Principal = Depends(require_permission("agent", "read")),
    session: AsyncSession = Depends(get_session),
):
    records = await list_checkpoints(
        session,
        principal.tenant_id,
        conversation_id=conversation_id,
        run_id=run_id,
    )
    return {"checkpoints": [_view(item, detail=False) for item in records], "total": len(records)}


@router.get("/{checkpoint_id}", summary="读取 checkpoint 详情")
async def get_checkpoint_detail(
    checkpoint_id: str,
    principal: Principal = Depends(require_permission("agent", "read")),
    session: AsyncSession = Depends(get_session),
):
    record = await get_checkpoint(session, principal.tenant_id, checkpoint_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "checkpoint 不存在或无权访问")
    return _view(record, detail=True)


@router.post(
    "/{checkpoint_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    summary="从 checkpoint 创建新 run",
)
async def resume_checkpoint(
    checkpoint_id: str,
    body: ResumeCheckpointIn,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
):
    if body.confirm_checkpoint_id != checkpoint_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "确认 checkpoint ID 不匹配")
    try:
        child = await create_resume_checkpoint(
            session,
            tenant_id=principal.tenant_id,
            checkpoint_id=checkpoint_id,
            new_run_id=uuid.uuid4().hex,
        )
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "checkpoint 不存在或无权访问"
        ) from exc
    await session.commit()
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="checkpoint.resume",
        resource="checkpoint",
        detail={
            "checkpoint_id": checkpoint_id,
            "child_checkpoint_id": child.checkpoint_id,
            "run_id": child.run_id,
        },
    )
    background_tasks.add_task(_run_resumed_checkpoint, child, principal)
    return {"accepted": True, "checkpoint": _view(child, detail=True)}


@router.post("/{checkpoint_id}/rollback", summary="受控回滚 checkpoint 文件变更")
async def rollback_checkpoint_files(
    checkpoint_id: str,
    body: RollbackCheckpointIn,
    principal: Principal = Depends(require_permission("agent", "manage")),
    session: AsyncSession = Depends(get_session),
):
    if body.confirm_checkpoint_id != checkpoint_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "确认 checkpoint ID 不匹配")
    try:
        record = await rollback_checkpoint(
            session,
            tenant_id=principal.tenant_id,
            checkpoint_id=checkpoint_id,
            task_id=body.task_id,
            source=body.source,
        )
        await session.commit()
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "checkpoint 或开发任务不存在"
        ) from exc
    except CheckpointRollbackError as exc:
        await session.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="checkpoint.rollback",
        resource="checkpoint",
        detail={
            "checkpoint_id": checkpoint_id,
            "task_id": body.task_id,
            "source": body.source,
            "rollback_commit": record.rollback_commit,
        },
    )
    return {"rolled_back": True, "checkpoint": _view(record, detail=True)}
