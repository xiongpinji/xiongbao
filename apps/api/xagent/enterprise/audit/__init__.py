"""审计层：追加式、防篡改审计日志（HMAC 哈希链）。

每条记录链接前一条的哈希，构成哈希链；任一条被篡改都会使后续校验失败。
Phase 1 提供内存实现 + 校验；Phase 5 落 Postgres + 签名 + 导出。
"""

from xagent.enterprise.audit.chain import (
    AuditEvent,
    AuditLog,
    get_audit_log,
    reset_audit_log,
)
from xagent.enterprise.audit.persistence import PostgresAuditLog, read_events

__all__ = [
    "AuditEvent",
    "AuditLog",
    "get_audit_log",
    "reset_audit_log",
    "PostgresAuditLog",
    "read_events",
]
