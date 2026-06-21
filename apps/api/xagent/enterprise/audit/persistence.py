"""审计持久化 + 导出。

Phase 5：内存哈希链（chain.py）为 lite 默认；full/enterprise 可换 PostgresAuditLog。
导出：按租户导出 JSON，含整链校验结果。接口与 AuditLog 一致（record/verify/list）。
"""

from __future__ import annotations

import json
from typing import Any

from xagent.enterprise.audit.chain import AuditEvent, AuditLog
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


class PostgresAuditLog:
    """Postgres 持久化审计链（full/enterprise）。

    占位实现：真实落库需建表 audit_events(seq,ts,tenant_id,actor,action,
    resource,detail,prev_hash,hash)，record/verify/list 走 SQL。接口与 AuditLog 一致，
    可在 factory 据模式替换。Phase 5 后段接 SQLAlchemy 落库。
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret
        logger.info("audit_postgres_init_placeholder")

    async def record(self, **kwargs: Any) -> AuditEvent:
        raise NotImplementedError("PostgresAuditLog 待落库实现；当前用内存 AuditLog")

    async def verify(self) -> tuple[bool, int | None]:
        raise NotImplementedError

    def list(self, tenant_id: str | None = None) -> list[AuditEvent]:
        raise NotImplementedError
