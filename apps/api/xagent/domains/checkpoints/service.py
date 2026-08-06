"""数据库 checkpoint 仓储、脱敏和父子恢复记录。"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.domains.checkpoints.models import CheckpointRecord
from xagent.infra.models.checkpoint import CheckpointORM

_MAX_MESSAGES = 30
_MAX_CONTENT_CHARS = 4000
_MAX_JSON_BYTES = 256 * 1024
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(\"?'?(?:[A-Za-z0-9_-]*(?:api[_-]?key|token|secret|password)"
    r"|authorization)\"?'?)(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)
_PROVIDER_TOKEN = re.compile(r"\b(?:sk|xak)-[A-Za-z0-9_-]{8,}\b")
_SENSITIVE_KEY = re.compile(
    r"(?i)^(?:[A-Za-z0-9_-]*(?:api[_-]?key|token|secret|password)|authorization)$"
)


def redact_checkpoint_text(value: str) -> str:
    def redact_assignment(match: re.Match[str]) -> str:
        quote = match.group(3)[0]
        replacement = f"{quote}[REDACTED]{quote}" if quote in "\"'" else "[REDACTED]"
        return f"{match.group(1)}{match.group(2)}{replacement}"

    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _SENSITIVE_ASSIGNMENT.sub(redact_assignment, value)
    return _PROVIDER_TOKEN.sub("[REDACTED]", value)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_checkpoint_text(value)[:_MAX_CONTENT_CHARS]
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.fullmatch(str(key)) else _redact_value(item)
            for key, item in value.items()
        }
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_checkpoint_text(str(value))[:_MAX_CONTENT_CHARS]


def _normalize_changed_files(changed_files: list[str], workspace: Path) -> list[str]:
    root = workspace.resolve()
    normalized: list[str] = []
    for raw in changed_files:
        candidate = Path(raw)
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        if not resolved.is_relative_to(root) or resolved == root:
            raise ValueError(f"unsafe_changed_file: {raw}")
        relative = resolved.relative_to(root).as_posix()
        if relative not in normalized:
            normalized.append(relative)
    return normalized


def _decode_list(value: str) -> list:
    parsed = json.loads(value or "[]")
    return parsed if isinstance(parsed, list) else []


def _record(row: CheckpointORM) -> CheckpointRecord:
    return CheckpointRecord(
        checkpoint_id=row.checkpoint_id,
        tenant_id=row.tenant_id,
        conversation_id=row.conversation_id,
        run_id=row.run_id,
        parent_checkpoint_id=row.parent_checkpoint_id,
        step=row.step,
        status=row.status,
        goal=row.goal,
        messages=_decode_list(row.messages_json),
        changed_files=[str(item) for item in _decode_list(row.changed_files_json)],
        resumed_run_id=row.resumed_run_id,
        rollback_source=row.rollback_source,
        rollback_commit=row.rollback_commit,
        rollback_error=row.rollback_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_checkpoint(
    session: AsyncSession,
    *,
    tenant_id: str,
    conversation_id: str,
    run_id: str,
    step: int,
    goal: str,
    messages: list[dict[str, Any]],
    changed_files: list[str],
    workspace: Path,
    parent_checkpoint_id: str = "",
    status: str = "available",
) -> CheckpointRecord:
    safe_messages = _redact_value(messages[-_MAX_MESSAGES:])
    safe_goal = redact_checkpoint_text(goal)[:_MAX_CONTENT_CHARS]
    safe_files = _normalize_changed_files(changed_files, workspace)
    messages_json = json.dumps(safe_messages, ensure_ascii=False, default=str)
    if len(messages_json.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ValueError("checkpoint_messages_too_large")
    row = CheckpointORM(
        checkpoint_id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        run_id=run_id,
        parent_checkpoint_id=parent_checkpoint_id,
        step=max(0, step),
        status=status,
        goal=safe_goal,
        messages_json=messages_json,
        changed_files_json=json.dumps(safe_files, ensure_ascii=False),
    )
    session.add(row)
    await session.flush()
    return _record(row)


async def get_checkpoint(
    session: AsyncSession, tenant_id: str, checkpoint_id: str
) -> CheckpointRecord | None:
    row = await session.scalar(
        select(CheckpointORM).where(
            CheckpointORM.tenant_id == tenant_id,
            CheckpointORM.checkpoint_id == checkpoint_id,
        )
    )
    return _record(row) if row is not None else None


async def list_checkpoints(
    session: AsyncSession,
    tenant_id: str,
    *,
    conversation_id: str = "",
    run_id: str = "",
) -> list[CheckpointRecord]:
    query = select(CheckpointORM).where(CheckpointORM.tenant_id == tenant_id)
    if conversation_id:
        query = query.where(CheckpointORM.conversation_id == conversation_id)
    if run_id:
        query = query.where(CheckpointORM.run_id == run_id)
    rows = await session.scalars(query.order_by(CheckpointORM.created_at.desc()))
    return [_record(row) for row in rows]


async def create_resume_checkpoint(
    session: AsyncSession,
    *,
    tenant_id: str,
    checkpoint_id: str,
    new_run_id: str,
) -> CheckpointRecord:
    parent = await get_checkpoint(session, tenant_id, checkpoint_id)
    if parent is None:
        raise LookupError(checkpoint_id)
    row = CheckpointORM(
        checkpoint_id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        conversation_id=parent.conversation_id,
        run_id=new_run_id,
        parent_checkpoint_id=parent.checkpoint_id,
        step=parent.step,
        status="pending",
        goal=parent.goal,
        messages_json=json.dumps(parent.messages, ensure_ascii=False, default=str),
        changed_files_json=json.dumps(parent.changed_files, ensure_ascii=False),
    )
    session.add(row)
    await session.flush()
    parent_row = await session.get(CheckpointORM, parent.checkpoint_id)
    assert parent_row is not None
    parent_row.resumed_run_id = new_run_id
    await session.flush()
    return _record(row)


async def update_checkpoint_status(
    session: AsyncSession,
    tenant_id: str,
    checkpoint_id: str,
    *,
    status: str,
    error: str = "",
) -> CheckpointRecord:
    row = await session.scalar(
        select(CheckpointORM).where(
            CheckpointORM.tenant_id == tenant_id,
            CheckpointORM.checkpoint_id == checkpoint_id,
        )
    )
    if row is None:
        raise LookupError(checkpoint_id)
    row.status = status
    row.rollback_error = error[:1000]
    await session.flush()
    return _record(row)
