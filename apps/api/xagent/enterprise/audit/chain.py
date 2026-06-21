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
from functools import lru_cache

from xagent.infra.settings import get_settings

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


class AuditLog:
    """内存哈希链审计日志（Phase 5 换持久化后端）。"""

    def __init__(self, secret: str) -> None:
        self._secret = secret
        self._events: list[AuditEvent] = []

    def record(
        self,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        resource: str,
        detail: dict | None = None,
    ) -> AuditEvent:
        seq = len(self._events)
        prev_hash = self._events[-1].hash if self._events else GENESIS
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
        return event

    def verify(self) -> tuple[bool, int | None]:
        """校验整条链。返回 (是否完整, 首个损坏的 seq 或 None)。"""
        prev_hash = GENESIS
        for ev in self._events:
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
        if tenant_id is None:
            return list(self._events)
        return [e for e in self._events if e.tenant_id == tenant_id]


@lru_cache
def get_audit_log() -> AuditLog:
    return AuditLog(secret=get_settings().security.jwt_secret)


def reset_audit_log() -> None:
    get_audit_log.cache_clear()
