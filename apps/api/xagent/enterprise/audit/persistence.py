"""审计持久化 + 导出。

持久化改造后：
- ``AuditLog``（chain.py）写透落 audit_events 表，启动从表尾恢复链状态。
- ``PostgresAuditLog`` 为纯 DB 后端的审计链实现（SQLite/Postgres 均可，
  经同步 SQLAlchemy），接口与 AuditLog 一致（record/verify/list）。
- ``read_events`` 为统一持久化读取接口：所有导出方（/audit/export*、
  /data/export/audit 等）应以此为准，保证数据源一致。
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from xagent.enterprise.audit.chain import (
    GENESIS,
    AuditEvent,
    AuditLog,
    _compute_hash,
    _ts_to_float,
)
from xagent.infra.logging import get_logger

logger = get_logger("xagent.audit")


def export_chain(log: AuditLog, tenant_id: str | None = None) -> dict[str, Any]:
    """导出审计链为可验证 JSON。"""
    events = log.list(tenant_id)
    ok, broken = log.verify()
    return {
        "tenant_id": tenant_id,
        "count": len(events),
        "integrity": {"valid": ok, "first_broken_seq": broken},
        "events": [e.to_dict() for e in events],
    }


def export_json(log: AuditLog, tenant_id: str | None = None) -> str:
    return json.dumps(export_chain(log, tenant_id), ensure_ascii=False, indent=2)


def read_events(tenant_id: str | None = None, limit: int | None = None) -> list[dict]:
    """统一持久化读取接口：直接读 audit_events 表（seq 升序）。

    返回字段与 ``AuditEvent.to_dict()`` 一致（ts 为 epoch 秒浮点）。
    DB 不可用时返回空列表（降级不阻断导出）。
    """
    try:
        from xagent.infra.repos.audit import load_all_audit_events_sync

        rows = load_all_audit_events_sync(tenant_id)
    except Exception as exc:
        logger.warning("audit_read_degraded", tenant_id=tenant_id, error=str(exc))
        return []
    events = [
        {
            "seq": r["seq"],
            "ts": _ts_to_float(r["ts"]),
            "tenant_id": r["tenant_id"],
            "actor": r["actor"],
            "action": r["action"],
            "resource": r["resource"],
            "detail": r["detail"],
            "prev_hash": r["prev_hash"],
            "hash": r["hash"],
        }
        for r in rows
    ]
    if limit is not None:
        events = events[-limit:]
    return events


class PostgresAuditLog:
    """DB 持久化审计链（SQLite/Postgres 均可，经同步 SQLAlchemy）。

    与 AuditLog 接口一致（record/verify/list），但无内存状态：
    每次操作直接读写 audit_events 表。可在 factory 按模式替换 AuditLog。
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret
        logger.info("audit_db_log_init")

    def _tail(self) -> dict | None:
        from xagent.infra.repos.audit import load_all_audit_events_sync

        rows = load_all_audit_events_sync()
        return rows[-1] if rows else None

    def record(
        self,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        resource: str,
        detail: dict | None = None,
    ) -> AuditEvent:
        from xagent.infra.repos.audit import persist_audit_event_sync

        tail = self._tail()
        seq = int(tail["seq"]) + 1 if tail else 0
        prev_hash = tail["hash"] if tail else GENESIS
        ts = time.time()
        detail = detail or {}
        h = _compute_hash(
            self._secret,
            seq=seq,
            ts=ts,
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource=resource,
            detail=detail,
            prev_hash=prev_hash,
        )
        persist_audit_event_sync(
            seq=seq,
            ts=datetime.fromtimestamp(ts, UTC),
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource=resource,
            detail=detail,
            prev_hash=prev_hash,
            hash_=h,
        )
        return AuditEvent(
            seq=seq,
            ts=ts,
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource=resource,
            detail=detail,
            prev_hash=prev_hash,
            hash=h,
        )

    def verify(self) -> tuple[bool, int | None]:
        """校验整条链。返回 (是否完整, 首个损坏的 seq 或 None)。"""
        prev_hash = GENESIS
        for ev in self.list():
            expect = _compute_hash(
                self._secret,
                seq=ev.seq,
                ts=ev.ts,
                tenant_id=ev.tenant_id,
                actor=ev.actor,
                action=ev.action,
                resource=ev.resource,
                detail=ev.detail,
                prev_hash=prev_hash,
            )
            if ev.prev_hash != prev_hash or ev.hash != expect:
                return False, ev.seq
            prev_hash = ev.hash
        return True, None

    def list(self, tenant_id: str | None = None) -> list[AuditEvent]:
        from xagent.infra.repos.audit import load_all_audit_events_sync

        rows = load_all_audit_events_sync(tenant_id)
        return [
            AuditEvent(
                seq=r["seq"],
                ts=_ts_to_float(r["ts"]),
                tenant_id=r["tenant_id"],
                actor=r["actor"],
                action=r["action"],
                resource=r["resource"],
                detail=r["detail"],
                prev_hash=r["prev_hash"],
                hash=r["hash"],
            )
            for r in rows
        ]
