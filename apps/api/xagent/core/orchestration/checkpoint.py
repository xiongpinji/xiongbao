"""数据库断点：长任务保存可审计、租户隔离的 checkpoint 历史。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from xagent.domains.checkpoints import (
    CheckpointRecord,
    create_checkpoint,
    list_checkpoints,
)
from xagent.infra.db import get_sessionmaker

_CHECKPOINT_INTERVAL = 5


async def save_checkpoint(
    conversation_id: str,
    run_id: str,
    step: int,
    messages: list[dict[str, Any]],
    changed_files: list[str],
    goal: str,
    *,
    tenant_id: str,
    workspace: Path,
    parent_checkpoint_id: str = "",
) -> CheckpointRecord:
    """独立事务保存 checkpoint，使运行中断或进程重启后仍可读取。"""
    async with get_sessionmaker()() as session:
        record = await create_checkpoint(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            step=step,
            goal=goal,
            messages=messages,
            changed_files=changed_files,
            workspace=workspace,
            parent_checkpoint_id=parent_checkpoint_id,
        )
        await session.commit()
        return record


async def load_checkpoint(
    conversation_id: str, *, tenant_id: str
) -> CheckpointRecord | None:
    """按租户加载会话最新 checkpoint；历史记录不会因读取或成功运行被删除。"""
    async with get_sessionmaker()() as session:
        records = await list_checkpoints(
            session, tenant_id, conversation_id=conversation_id
        )
    return records[0] if records else None


def should_checkpoint(step: int) -> bool:
    return step > 0 and step % _CHECKPOINT_INTERVAL == 0
