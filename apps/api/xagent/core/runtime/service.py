"""统一 Runtime 聚合 service。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.runtime.models import RuntimeRun, RuntimeTaskRef
from xagent.infra.models.agent_task import AgentTaskORM
from xagent.infra.models.artifact import ArtifactORM
from xagent.infra.repos.evidence import load_evidence_records
from xagent.infra.repos.spine import load_spine_linkage_by_run_id, load_spine_task_reference
from xagent.infra.repos.workflow import load_workflow_run_by_id, load_workflow_runs


def _is_schema_mismatch(exc: Exception, table_name: str) -> bool:
    parts = [str(exc)]
    for attr in ("orig", "statement", "params"):
        value = getattr(exc, attr, None)
        if value is not None:
            parts.append(str(value))
    lowered = " ".join(parts).lower()
    return table_name.lower() in lowered and any(
        token in lowered
        for token in (
            "no such table",
            "does not exist",
            "no such column",
            "unknown column",
            "undefined column",
            "has no column named",
        )
    )


def _build_workflow_delivery_fallback(workflow_view: dict[str, Any] | None) -> dict[str, Any]:
    if workflow_view is None:
        return {}
    from xagent.api.v1.workflows import build_workflow_delivery_summary

    return build_workflow_delivery_summary(workflow_view)


def _build_task_delivery_fallback(task_view: dict[str, Any] | None) -> dict[str, Any]:
    if task_view is None:
        return {}

    run_id = str(task_view.get("run_id") or "").strip()
    task_id = str(task_view.get("task_id") or run_id).strip()
    kind = str(task_view.get("kind") or "runtime.task")
    status = str(task_view.get("status") or "pending")
    summary = f"后台任务 {kind} 当前状态为 {status}。"
    replay = None
    if run_id and task_id:
        replay = {
            "mode": "task_detail",
            "label": "查看后台任务",
            "run_id": run_id,
            "task_id": task_id,
            "api_path": f"/api/v1/tasks/{task_id}",
            "console_path": f"/runs/{run_id}",
        }
    resume = None
    if status in {"pending", "running"} and replay is not None:
        resume = {
            "mode": "task_follow",
            "label": "继续查看后台任务",
            "run_id": run_id,
            "task_id": task_id,
            "status": status,
            "api_path": replay["api_path"],
            "console_path": replay["console_path"],
        }

    return {
        "status": "ready"
        if status == "succeeded"
        else "blocked"
        if status == "failed"
        else "pending",
        "channel": "task_runtime",
        "kind": kind,
        "summary": summary,
        "replay": replay,
        "resume": resume,
    }


def _build_delivery_artifact_projection(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for artifact in artifacts:
        projected.append(
            {
                "artifact_id": str(artifact.get("artifact_id") or ""),
                "task_id": str(artifact.get("task_id") or ""),
                "kind": str(artifact.get("kind") or "artifact"),
                "name": str(artifact.get("name") or ""),
                "uri": str(artifact.get("uri") or ""),
                "content_type": str(artifact.get("content_type") or "application/octet-stream"),
                "preview_summary": deepcopy(artifact.get("preview_summary") or {}),
            }
        )
    return projected


def _normalize_risks(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    risks: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            risks.append(text)
    return risks


def _ensure_validation_contract(validation: dict[str, Any] | None) -> dict[str, Any]:
    merged = deepcopy(validation) if isinstance(validation, dict) else {}
    merged["risks"] = _normalize_risks(merged.get("risks"))
    return merged


def _normalize_failure_bundle(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized = deepcopy(value)
    if "code" in normalized and normalized.get("code") is not None:
        normalized["code"] = str(normalized.get("code") or "").strip()
    if "source" in normalized and normalized.get("source") is not None:
        normalized["source"] = str(normalized.get("source") or "").strip()
    if "message" in normalized and normalized.get("message") is not None:
        normalized["message"] = str(normalized.get("message") or "").strip()
    if "blocking_step" in normalized and normalized.get("blocking_step") is not None:
        normalized["blocking_step"] = str(normalized.get("blocking_step") or "").strip()
    if "step_name" in normalized and normalized.get("step_name") is not None:
        normalized["step_name"] = str(normalized.get("step_name") or "").strip() or None
    if "recommended_action" in normalized and normalized.get("recommended_action") is not None:
        normalized["recommended_action"] = (
            str(normalized.get("recommended_action") or "").strip() or None
        )
    if "retryable" in normalized:
        normalized["retryable"] = bool(normalized.get("retryable"))
    return normalized


def _ensure_delivery_contract(delivery: dict[str, Any] | None) -> dict[str, Any]:
    merged = deepcopy(delivery) if isinstance(delivery, dict) else {}
    merged["risks"] = _normalize_risks(merged.get("risks"))
    merged["failure"] = _normalize_failure_bundle(merged.get("failure"))
    return merged


def _merge_delivery_bundle(
    *,
    delivery: dict[str, Any],
    validation: dict[str, Any],
    artifacts: list[dict[str, Any]],
    workflow_view: dict[str, Any] | None,
    task_view: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = _ensure_delivery_contract(delivery)
    fallback = (
        _build_workflow_delivery_fallback(workflow_view)
        if workflow_view is not None
        else _build_task_delivery_fallback(task_view)
    )
    if "summary" not in merged or not str(merged.get("summary") or "").strip():
        merged["summary"] = str(fallback.get("summary") or "").strip()
    if "kind" not in merged or not str(merged.get("kind") or "").strip():
        merged["kind"] = str(fallback.get("kind") or "runtime.delivery")
    if "status" not in merged or not str(merged.get("status") or "").strip():
        merged["status"] = str(fallback.get("status") or "pending")
    merged["artifacts"] = _build_delivery_artifact_projection(artifacts)
    merged["validation"] = deepcopy(validation)
    if not isinstance(merged.get("replay"), dict):
        merged["replay"] = deepcopy(fallback.get("replay"))
    if merged.get("resume") is None and fallback.get("resume") is not None:
        merged["resume"] = deepcopy(fallback.get("resume"))
    elif "resume" not in merged:
        merged["resume"] = None
    validation_risks = _normalize_risks(validation.get("risks"))
    combined_risks: list[str] = []
    for item in [*merged.get("risks", []), *validation_risks]:
        if item and item not in combined_risks:
            combined_risks.append(item)
    merged["risks"] = combined_risks
    return merged


def _decode_json_payload(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def _resolve_spine_linkage(
    session: AsyncSession,
    *,
    tenant_id: str,
    run_id: str,
    db_task: AgentTaskORM | None,
    task_view: dict[str, Any] | None,
    workflow_view: dict[str, Any] | None,
) -> dict[str, str]:
    input_payload = (
        _decode_json_payload(db_task.input_payload)
        if db_task is not None
        else deepcopy((task_view or {}).get("input") or {})
    )
    if not input_payload and isinstance(workflow_view, dict):
        input_payload = {
            "goal_id": str(workflow_view.get("goal_id") or ""),
            "spine_task_id": str(workflow_view.get("spine_task_id") or ""),
        }
    goal_id = str(input_payload.get("goal_id") or "").strip()
    spine_task_id = str(input_payload.get("spine_task_id") or "").strip()
    if goal_id and spine_task_id:
        reference = await load_spine_task_reference(
            session,
            tenant_id=tenant_id,
            goal_id=goal_id,
            spine_task_id=spine_task_id,
        )
        if reference is not None:
            return {
                "goal_id": reference["goal_id"],
                "initiative_id": reference["initiative_id"],
                "spine_task_id": reference["task_id"],
            }
    return await load_spine_linkage_by_run_id(
        session,
        tenant_id=tenant_id,
        run_id=run_id,
    )


def _build_runtime_task_view(row: AgentTaskORM) -> dict[str, Any]:
    runtime_run = RuntimeRun(
        run_id=row.run_id,
        task=RuntimeTaskRef(
            task_id=row.task_id,
            kind=row.kind,
            source=row.source,
            intent_type=row.intent_type,
            route_source=row.route_source,
        ),
        tenant_id=row.tenant_id,
        owner_id=row.owner_id,
        status=row.status,
        backend=row.backend,
        input_payload=_decode_json_payload(row.input_payload),
        result=_decode_json_payload(row.result_payload),
        error=row.error,
        created_at=row.created_at.isoformat() if row.created_at else None,
        started_at=row.started_at.isoformat() if row.started_at else None,
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )
    return runtime_run.to_view()


async def _load_db_runtime_tasks_by_run(
    session: AsyncSession,
    *,
    run_id: str,
    tenant_id: str,
) -> list[AgentTaskORM]:
    stmt = (
        select(AgentTaskORM)
        .where(
            AgentTaskORM.run_id == run_id,
            AgentTaskORM.tenant_id == tenant_id,
        )
        .order_by(AgentTaskORM.created_at.asc(), AgentTaskORM.task_id.asc())
    )
    try:
        result = await session.execute(stmt)
    except Exception as exc:
        if _is_schema_mismatch(exc, "agent_tasks"):
            return []
        raise
    return list(result.scalars())


async def _load_db_runtime_tasks_by_ids(
    session: AsyncSession,
    *,
    task_ids: set[str],
    tenant_id: str,
) -> list[AgentTaskORM]:
    if not task_ids:
        return []
    stmt = (
        select(AgentTaskORM)
        .where(
            AgentTaskORM.task_id.in_(task_ids),
            AgentTaskORM.tenant_id == tenant_id,
        )
        .order_by(AgentTaskORM.created_at.asc(), AgentTaskORM.task_id.asc())
    )
    try:
        result = await session.execute(stmt)
    except Exception as exc:
        if _is_schema_mismatch(exc, "agent_tasks"):
            return []
        raise
    return list(result.scalars())


async def _load_db_runtime_task(
    session: AsyncSession,
    *,
    run_id: str,
    tenant_id: str,
) -> AgentTaskORM | None:
    tasks = await _load_db_runtime_tasks_by_run(session, run_id=run_id, tenant_id=tenant_id)
    return tasks[0] if tasks else None


async def _load_workflow_view(
    session: AsyncSession,
    *,
    run_id: str,
    tenant_id: str,
) -> dict[str, Any] | None:
    exact = await load_workflow_run_by_id(session, tenant_id, run_id)
    if exact is not None:
        return exact

    runs = await load_workflow_runs(session, tenant_id, limit=200)
    for view in runs:
        if view.get("run_id") == run_id:
            return view
    return None


async def _load_artifacts(
    session: AsyncSession,
    *,
    run_id: str,
    tenant_id: str,
) -> tuple[list[dict[str, Any]], bool]:
    stmt = (
        select(ArtifactORM)
        .where(
            ArtifactORM.run_id == run_id,
            ArtifactORM.tenant_id == tenant_id,
        )
        .order_by(ArtifactORM.created_at.asc())
    )
    try:
        result = await session.execute(stmt)
    except Exception as exc:
        if _is_schema_mismatch(exc, "artifacts"):
            return [], False
        raise
    artifacts: list[dict[str, Any]] = []
    for row in result.scalars():
        artifacts.append(
            {
                "artifact_id": row.artifact_id,
                "run_id": row.run_id,
                "task_id": row.task_id,
                "tenant_id": row.tenant_id,
                "kind": row.kind,
                "name": row.name,
                "uri": row.uri,
                "content_type": row.content_type,
                "size_bytes": row.size_bytes,
                "checksum": row.checksum,
                "validation_summary": _decode_json_payload(row.validation_summary),
                "delivery_summary": _decode_json_payload(row.delivery_summary),
                "lineage_summary": _decode_json_payload(row.lineage_summary),
                "preview_summary": _decode_json_payload(row.preview_summary),
            }
        )
    return artifacts, True


def _dedupe_task_views(task_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for task_view in task_views:
        task_id = str(task_view.get("task_id") or "")
        if not task_id or task_id in seen:
            continue
        seen.add(task_id)
        deduped.append(task_view)
    return deduped


async def _load_related_tasks(
    session: AsyncSession,
    *,
    primary_task: AgentTaskORM | None,
    sibling_tasks: list[AgentTaskORM],
    artifacts: list[dict[str, Any]],
    tenant_id: str,
) -> list[dict[str, Any]]:
    if primary_task is None:
        return []

    lineage = _decode_json_payload(primary_task.lineage_summary)
    referenced_task_ids: set[str] = set()
    parent_task_id = str(lineage.get("parent_task_id") or "").strip()
    if parent_task_id:
        referenced_task_ids.add(parent_task_id)

    artifact_ids = {
        str(artifact_id).strip()
        for artifact_id in (lineage.get("artifact_ids") or [])
        if str(artifact_id).strip()
    }
    for artifact in artifacts:
        artifact_lineage = artifact.get("lineage_summary") or {}
        for artifact_id in artifact_lineage.get("artifact_ids") or []:
            value = str(artifact_id).strip()
            if value:
                artifact_ids.add(value)

    if artifact_ids:
        artifact_stmt = select(ArtifactORM).where(
            ArtifactORM.artifact_id.in_(artifact_ids),
            ArtifactORM.tenant_id == tenant_id,
        )
        artifact_rows = (await session.execute(artifact_stmt)).scalars().all()
        for row in artifact_rows:
            if row.task_id and row.task_id != primary_task.task_id:
                referenced_task_ids.add(row.task_id)
            artifact_lineage = _decode_json_payload(row.lineage_summary)
            parent_from_artifact = str(artifact_lineage.get("parent_task_id") or "").strip()
            if parent_from_artifact and parent_from_artifact != primary_task.task_id:
                referenced_task_ids.add(parent_from_artifact)

    related_rows: list[AgentTaskORM] = []
    related_rows.extend(
        row
        for row in sibling_tasks
        if row.task_id != primary_task.task_id and row.task_id not in referenced_task_ids
    )
    related_rows.extend(
        row
        for row in await _load_db_runtime_tasks_by_ids(
            session,
            task_ids=referenced_task_ids,
            tenant_id=tenant_id,
        )
        if row.task_id != primary_task.task_id
    )
    return _dedupe_task_views([_build_runtime_task_view(row) for row in related_rows])


async def get_runtime_run_detail(
    session: AsyncSession,
    *,
    run_id: str,
    tenant_id: str,
) -> dict[str, Any] | None:
    from xagent.api.v1.creative_studio import get_creative_runtime_view
    from xagent.api.v1.tasks import get_task_runtime_view

    task_view = await get_task_runtime_view(run_id, tenant_id)
    creative_view = get_creative_runtime_view(run_id, tenant_id)

    db_tasks = await _load_db_runtime_tasks_by_run(session, run_id=run_id, tenant_id=tenant_id)
    db_task = db_tasks[0] if db_tasks else None
    workflow_view = await _load_workflow_view(session, run_id=run_id, tenant_id=tenant_id)

    if task_view is None and creative_view is None and db_task is None and workflow_view is None:
        return None

    evidence = await load_evidence_records(session, tenant_id, run_id=run_id)
    artifacts, artifacts_available = await _load_artifacts(
        session, run_id=run_id, tenant_id=tenant_id
    )

    task = None
    if db_task is not None:
        task = _build_runtime_task_view(db_task)
    elif creative_view is not None:
        task = deepcopy(creative_view.get("task"))
    elif task_view is not None:
        task = deepcopy(task_view)

    validation = _ensure_validation_contract(
        _decode_json_payload(db_task.validation_summary)
        if db_task is not None
        else deepcopy((creative_view or {}).get("validation") or {})
    )
    delivery_source = (
        _decode_json_payload(db_task.delivery_summary)
        if db_task is not None
        else deepcopy((creative_view or {}).get("delivery") or {})
    )
    has_delivery_source = bool(delivery_source)
    delivery = _ensure_delivery_contract(delivery_source)
    if not has_delivery_source and task is not None:
        delivery = _ensure_delivery_contract(_build_task_delivery_fallback(task))
    if db_task is None and creative_view is None and workflow_view is not None:
        delivery = _ensure_delivery_contract(_build_workflow_delivery_fallback(workflow_view))
    delivery = _merge_delivery_bundle(
        delivery=delivery,
        validation=validation,
        artifacts=artifacts,
        workflow_view=workflow_view,
        task_view=task,
    )
    related_tasks = (
        await _load_related_tasks(
            session,
            primary_task=db_task,
            sibling_tasks=db_tasks,
            artifacts=artifacts,
            tenant_id=tenant_id,
        )
        if db_task is not None
        else deepcopy((creative_view or {}).get("related_tasks") or [])
    )
    spine = await _resolve_spine_linkage(
        session,
        tenant_id=tenant_id,
        run_id=run_id,
        db_task=db_task,
        task_view=task,
        workflow_view=workflow_view,
    )

    return {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "task": task,
        "workflow": workflow_view or deepcopy((creative_view or {}).get("workflow")),
        "evidence": evidence or deepcopy((creative_view or {}).get("evidence") or []),
        "artifacts": (artifacts if artifacts_available or creative_view is None else []),
        "validation": validation,
        "delivery": delivery,
        "related_tasks": related_tasks,
        "spine": spine,
    }
