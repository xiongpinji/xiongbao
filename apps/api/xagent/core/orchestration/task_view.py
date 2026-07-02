"""Task view helper：为未来 /runs 聚合固化 task contract foundation。"""

from __future__ import annotations

from typing import Any

from xagent.core.runtime.models import RuntimeRun, RuntimeTaskRef


def build_task_view(
    *,
    task_id: str,
    run_id: str | None,
    tenant_id: str,
    owner_id: str,
    kind: str,
    backend: str,
    status: str | None,
    input_payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    error: Any = "",
    created_at: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    updated_at: str | None = None,
    source: str | None = None,
    intent_type: str | None = None,
    route_source: str | None = None,
) -> dict[str, Any]:
    # 兼容策略：在 /runs 聚合落地前，task API 暂以 task_id 兼作 run_id。
    runtime_run = RuntimeRun(
        run_id=run_id or task_id,
        task=RuntimeTaskRef(
            task_id=task_id,
            kind=kind,
            source=source,
            intent_type=intent_type,
            route_source=route_source,
        ),
        tenant_id=tenant_id,
        owner_id=owner_id,
        status=status or "pending",
        backend=backend,
        input_payload=input_payload or {},
        result=result or {},
        error=str(error or ""),
        created_at=created_at,
        started_at=started_at,
        finished_at=finished_at,
        updated_at=updated_at,
    )
    return runtime_run.to_view()
