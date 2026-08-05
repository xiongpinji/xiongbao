"""HMAC 哈希链审计日志。

每条记录：seq、ts、tenant_id、actor、action、resource、detail、prev_hash、hash。
hash = HMAC_SHA256(secret, f"{seq}|{ts}|{tenant}|{actor}|{action}|{resource}|{detail}|{prev_hash}")
校验时重算逐条比对 + 链接关系，发现断裂即定位被篡改位置。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache

from xagent.infra.logging import get_logger
from xagent.infra.settings import get_settings

logger = get_logger("xagent.audit.chain")

GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditEvent:
    seq: int
    ts: float
    tenant_id: str
    actor: str
    action: str
    resource: str
    detail: dict
    prev_hash: str
    hash: str

    def to_dict(self) -> dict:
        return asdict(self)


def _compute_hash(secret: str, *, seq: int, ts: float, tenant_id: str, actor: str,
                  action: str, resource: str, detail: dict, prev_hash: str) -> str:
    payload = "|".join(
        [
            str(seq),
            f"{ts:.6f}",
            tenant_id,
            actor,
            action,
            resource,
            json.dumps(detail, sort_keys=True, ensure_ascii=False),
            prev_hash,
        ]
    )
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _ts_to_float(ts) -> float:
    """DB datetime -> epoch 秒（naive 视为 UTC）。"""
    if ts is None:
        return 0.0
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.timestamp()
    return float(ts)


class AuditLog:
    """哈希链审计日志：内存链为权威校验源，可选写透持久化到 audit_events 表。

    - ``persist=False``（默认）：纯内存链，自包含隔离实例（测试/临时用途），
      不触 DB、不受 DB 存量链影响。
    - ``persist=True``（``get_audit_log()`` 工厂使用）：record 同步落库
      （显式 seq，DB 与内存链对齐）；实例化时从表尾恢复链状态，
      重启后 seq / prev_hash 连续，verify 跨重启有效；DB 不可用降级纯内存。
    """

    def __init__(self, secret: str, *, persist: bool = False) -> None:
        self._secret = secret
        self._events: list[AuditEvent] = []
        # DB 可用性标记：恢复或写透失败后降级纯内存
        self._db_ok = persist
        # seq 下限：断链隔离时越过存量最大 seq，防止新事件 PK 冲突
        self._seq_floor = 0
        if persist:
            self._restore_from_db()

    # ─── 持久化 ───

    def _restore_from_db(self) -> None:
        try:
            from xagent.infra.repos.audit import load_all_audit_events_sync

            rows = load_all_audit_events_sync()
        except Exception as exc:
            self._db_ok = False
            logger.warning("audit_restore_degraded", error=str(exc))
            return
        events = [
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
        # 恢复时先校验：断链（历史被篡改 / 跨 secret / 异源写入）不装入运行时链，
        # 防止脏历史导致 verify 永久失败；DB 行保留供取证，新链从 GENESIS 重起。
        ok, broken = self._verify_events(events)
        if not ok:
            logger.error(
                "audit_chain_broken_on_restore",
                first_broken_seq=broken,
                count=len(events),
            )
            self._seq_floor = max((e.seq for e in events), default=-1) + 1
            return
        self._events = events
        if self._events:
            logger.info("audit_chain_restored", count=len(self._events))

    def _persist(self, event: AuditEvent) -> None:
        if not self._db_ok:
            return
        try:
            from xagent.infra.repos.audit import persist_audit_event_sync

            persist_audit_event_sync(
                seq=event.seq,
                ts=datetime.fromtimestamp(event.ts, UTC),
                tenant_id=event.tenant_id,
                actor=event.actor,
                action=event.action,
                resource=event.resource,
                detail=event.detail,
                prev_hash=event.prev_hash,
                hash_=event.hash,
            )
        except Exception as exc:
            self._db_ok = False
            logger.warning("audit_persist_degraded", error=str(exc))

    def record(
        self,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        resource: str,
        detail: dict | None = None,
    ) -> AuditEvent:
        detail = detail or {}
        # seq 取链尾 +1（而非 len）：与 DB 显式 seq 对齐，容忍存量数据非 0 起始；
        # 断链隔离后 seq_floor 越过存量最大 seq
        seq = max(
            self._events[-1].seq + 1 if self._events else 0,
            self._seq_floor,
        )
        prev_hash = self._events[-1].hash if self._events else GENESIS
        ts = time.time()
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
        event = AuditEvent(
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
        self._events.append(event)
        self._persist(event)
        return event

    def _verify_events(self, events: list[AuditEvent]) -> tuple[bool, int | None]:
        prev_hash = GENESIS
        for ev in events:
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

    def verify(self) -> tuple[bool, int | None]:
        """校验整条链。返回 (是否完整, 首个损坏的 seq 或 None)。"""
        return self._verify_events(self._events)

    def list(self, tenant_id: str | None = None) -> list[AuditEvent]:
        if tenant_id is None:
            return list(self._events)
        return [e for e in self._events if e.tenant_id == tenant_id]


@lru_cache
def get_audit_log() -> AuditLog:
    """应用级审计链单例：持久化到 audit_events 表，启动恢复链状态。"""
    return AuditLog(secret=get_settings().security.jwt_secret, persist=True)


def reset_audit_log() -> None:
    get_audit_log.cache_clear()
