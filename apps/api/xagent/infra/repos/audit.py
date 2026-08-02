"""审计 repository：哈希链事件落库（与内存 AuditLog 并行，互为备份）。

内存链仍为权威校验源（含 prev_hash 链接）；DB 为查询/归档备份。
verify() 走内存链；list 可从 DB 取（支持跨重启历史查询）。
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.infra.logging import get_logger
from xagent.infra.models.audit import AuditEventORM

logger = get_logger("xagent.repos.audit")


async def persist_audit_event(
    session: AsyncSession,
    *,
    ts,
    tenant_id: str,
    actor: str,
    action: str,
    resource: str,
    detail: dict,
    prev_hash: str,
    hash_: str,
) -> None:
    try:
        session.add(
            AuditEventORM(
                ts=ts,
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                resource=resource,
                detail=json.dumps(detail, ensure_ascii=False),
                prev_hash=prev_hash,
                hash=hash_,
            )
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.warning("persist_audit_failed", tenant_id=tenant_id, error=str(exc))


async def load_audit_events(
    session: AsyncSession, tenant_id: str, limit: int = 200
) -> list[dict]:
    try:
        stmt = (
            select(AuditEventORM)
            .where(AuditEventORM.tenant_id == tenant_id)
            .order_by(AuditEventORM.seq.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [
            {
                "seq": r.seq,
                "ts": r.ts.isoformat() if r.ts else None,
                "tenant_id": r.tenant_id,
                "actor": r.actor,
                "action": r.action,
                "resource": r.resource,
                "detail": json.loads(r.detail) if r.detail else {},
                "prev_hash": r.prev_hash,
                "hash": r.hash,
            }
            for r in result.scalars()
        ]
    except Exception as exc:
        logger.warning("load_audit_failed", tenant_id=tenant_id, error=str(exc))
        return []


# ─── 同步持久化（供同步接口的 AuditLog 哈希链使用） ───

from xagent.infra.repos.sync_db import sync_session  # noqa: E402


def persist_audit_event_sync(
    *,
    seq: int,
    ts,
    tenant_id: str,
    actor: str,
    action: str,
    resource: str,
    detail: dict,
    prev_hash: str,
    hash_: str,
) -> None:
    """写透一条链事件。显式指定 seq，保证 DB seq 与内存链 seq 对齐。"""
    with sync_session() as s:
        s.add(
            AuditEventORM(
                seq=seq,
                ts=ts,
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                resource=resource,
                detail=json.dumps(detail, ensure_ascii=False),
                prev_hash=prev_hash,
                hash=hash_,
            )
        )


def load_all_audit_events_sync(tenant_id: str | None = None) -> list[dict]:
    """按 seq 升序读取链事件（启动恢复链状态 / 统一读取接口）。"""
    with sync_session() as s:
        stmt = select(AuditEventORM).order_by(AuditEventORM.seq.asc())
        if tenant_id is not None:
            stmt = stmt.where(AuditEventORM.tenant_id == tenant_id)
        rows = (s.execute(stmt)).scalars().all()
        return [
            {
                "seq": r.seq,
                "ts": r.ts,
                "tenant_id": r.tenant_id,
                "actor": r.actor,
                "action": r.action,
                "resource": r.resource,
                "detail": json.loads(r.detail) if r.detail else {},
                "prev_hash": r.prev_hash,
                "hash": r.hash,
            }
            for r in rows
        ]
