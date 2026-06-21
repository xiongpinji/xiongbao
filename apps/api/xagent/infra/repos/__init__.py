"""Repository 层：封装 DB 持久化读写，供 services/routes 调用。

lite 模式仍走内存；full/enterprise 走 DB。Repository 接受 AsyncSession，
路由通过 get_session 依赖注入。失败不阻断主流程（持久化是增强，非强约束）。
"""

from xagent.infra.repos.audit import load_audit_events, persist_audit_event
from xagent.infra.repos.billing import persist_billing_record
from xagent.infra.repos.workflow import load_workflow_runs, persist_workflow_run

__all__ = [
    "persist_workflow_run",
    "load_workflow_runs",
    "persist_billing_record",
    "persist_audit_event",
    "load_audit_events",
]
