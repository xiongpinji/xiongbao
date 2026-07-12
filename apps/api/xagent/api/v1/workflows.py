"""工作流路由：创建/执行/审批/查看视图。强鉴权 + RBAC + 租户隔离。"""

from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.workflow import (
    ApprovalGate,
    WorkflowEngine,
    WorkflowSpec,
    WorkflowStep,
    get_engine,
)
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session, get_sessionmaker
from xagent.infra.logging import get_logger
from xagent.infra.models.agent_task import AgentTaskORM
from xagent.infra.repos.evidence import persist_evidence_bundle
from xagent.infra.repos.spine import attach_run_to_task, load_spine_task_reference
from xagent.infra.repos.workflow import (
    load_workflow_run_by_id,
    load_workflow_runs,
    persist_workflow_run,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])
logger = get_logger("xagent.api.workflows")


class StepIn(BaseModel):
    id: str
    name: str
    role: str = "general"
    goal: str = ""
    depends_on: list[str] = Field(default_factory=list)
    compensation_role: str | None = None
    compensation_goal: str | None = None
    approver_role: str | None = None
    approval_message: str = ""


class SpecIn(BaseModel):
    name: str
    goal_id: str = ""
    spine_task_id: str = ""
    description: str = ""
    steps: list[StepIn]


def _to_spec(body: SpecIn) -> WorkflowSpec:
    steps = [
        WorkflowStep(
            id=s.id,
            name=s.name,
            role=s.role,
            goal=s.goal,
            depends_on=s.depends_on,
            compensation_role=s.compensation_role,
            compensation_goal=s.compensation_goal,
            approval=ApprovalGate(approver_role=s.approver_role, message=s.approval_message)
            if s.approver_role
            else None,
        )
        for s in body.steps
    ]
    return WorkflowSpec(name=body.name, description=body.description, steps=steps)


def _decode_json_payload(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def _resolve_spine_contract(
    *,
    principal: Principal,
    goal_id: str,
    spine_task_id: str,
) -> tuple[str, str, bool]:
    resolved_goal_id = goal_id.strip()
    resolved_spine_task_id = spine_task_id.strip()
    if not resolved_goal_id and not resolved_spine_task_id:
        return "", "", False
    if not resolved_goal_id or not resolved_spine_task_id:
        raise ValueError("spine goal_id 与 spine_task_id 必须同时提供")

    async with get_sessionmaker()() as session:
        reference = await load_spine_task_reference(
            session,
            tenant_id=principal.tenant_id,
            goal_id=resolved_goal_id,
            spine_task_id=resolved_spine_task_id,
        )
    if reference is None:
        raise ValueError("spine task 不存在或与 goal_id 不匹配")
    return resolved_goal_id, resolved_spine_task_id, True


def _apply_spine_provenance(view: dict, linkage: dict[str, str] | None) -> None:
    if linkage is None:
        return
    goal_id = str(linkage.get("goal_id") or "").strip()
    task_id = str(linkage.get("task_id") or "").strip()
    if goal_id:
        view["goal_id"] = goal_id
    if task_id:
        view["spine_task_id"] = task_id


def build_workflow_replay_pointer(run_id: str) -> dict[str, str] | None:
    run_id = str(run_id or "").strip()
    if not run_id:
        return None
    return {
        "mode": "workflow_replay",
        "label": "回放工作流",
        "run_id": run_id,
        "api_path": f"/api/v1/workflows/{run_id}",
        "console_path": f"/runs/{run_id}",
    }


def build_workflow_resume_pointer(run_view: dict) -> dict | None:
    run_id = str(run_view.get("run_id") or "").strip()
    if not run_id:
        return None
    for step in run_view.get("steps") or []:
        step_id = str(step.get("id") or "").strip()
        step_status = str(step.get("status") or "").strip()
        if step_id and step_status == "awaiting_approval":
            encoded_step_id = quote(step_id, safe="")
            return {
                "mode": "workflow_approval",
                "label": f"继续审批 {step_id}",
                "run_id": run_id,
                "step_id": step_id,
                "status": step_status,
                "approve_path": f"/api/v1/workflows/{run_id}/approve/{encoded_step_id}",
                "deny_path": f"/api/v1/workflows/{run_id}/deny/{encoded_step_id}",
                "console_path": f"/runs/{run_id}",
            }
    return None


def build_workflow_failure_bundle(run_view: dict) -> dict | None:
    timeline = run_view.get("timeline") or []
    steps = run_view.get("steps") or []
    status = str(run_view.get("status") or "pending")
    if status not in {"failed", "rolled_back", "cancelled"}:
        return None

    blocked_step = next(
        (
            step
            for step in steps
            if str(step.get("status") or "") in {"failed", "rolled_back", "cancelled", "skipped"}
        ),
        None,
    )
    denied_event = next(
        (event for event in reversed(timeline) if str(event.get("kind") or "") == "denied"),
        None,
    )
    blocking_step = str(
        (blocked_step or {}).get("id")
        or (denied_event or {}).get("step_id")
        or "workflow"
    ).strip()
    step_name = str((blocked_step or {}).get("name") or "").strip() or None
    if status == "cancelled":
        message = (
            f"审批步骤 {blocking_step} 被拒绝，工作流已取消。"
            if blocking_step != "workflow"
            else "工作流已取消。"
        )
    elif status == "rolled_back":
        message = (
            f"步骤 {blocking_step} 执行失败，已触发补偿回滚。"
            if blocking_step != "workflow"
            else "工作流执行失败，已触发补偿回滚。"
        )
    else:
        message = (
            f"步骤 {blocking_step} 执行失败，工作流已阻塞。"
            if blocking_step != "workflow"
            else "工作流执行失败，当前已阻塞。"
        )

    detail_message = str((blocked_step or {}).get("error") or "").strip()
    details: dict[str, object] = {
        "workflow_status": status,
        "completed_steps": sum(1 for step in steps if step.get("status") == "succeeded"),
        "step_count": len(steps),
    }
    if detail_message:
        details["error"] = detail_message
    if denied_event is not None:
        details["denied_by"] = denied_event.get("detail")

    return {
        "code": status,
        "source": "workflow",
        "message": message,
        "blocking_step": blocking_step,
        "step_name": step_name,
        "retryable": status == "failed",
        "recommended_action": (
            "检查失败步骤后重新运行工作流"
            if status in {"failed", "rolled_back"}
            else "请确认审批结论后重新提交工作流"
        ),
        "details": details,
    }


def build_workflow_delivery_summary(run_view: dict) -> dict:
    timeline = run_view.get("timeline") or []
    steps = run_view.get("steps") or []
    status = str(run_view.get("status") or "pending")
    spec_name = str(run_view.get("spec_name") or "工作流")
    step_count = len(steps)
    completed_steps = sum(1 for step in steps if step.get("status") == "succeeded")
    highlights = [
        str(step.get("name") or step.get("id") or "步骤")
        for step in steps[:3]
        if step.get("name") or step.get("id")
    ]
    workflow = {
        "spec_name": spec_name,
        "status": status,
        "step_count": step_count,
        "completed_steps": completed_steps,
        "timeline_events": len(timeline),
        "highlights": highlights,
    }
    replay = build_workflow_replay_pointer(str(run_view.get("run_id") or ""))
    resume = build_workflow_resume_pointer(run_view)
    failure = build_workflow_failure_bundle(run_view)
    if status == "completed":
        delivery_status = "ready"
        summary = f"工作流 {spec_name} 已完成，{completed_steps}/{step_count} 个步骤成功。"
    elif status == "awaiting_approval":
        delivery_status = "pending"
        summary = f"工作流 {spec_name} 等待审批，当前已完成 {completed_steps}/{step_count} 个步骤。"
    elif status in {"failed", "rolled_back", "cancelled"}:
        delivery_status = "blocked"
        summary = f"工作流 {spec_name} 未完成，当前状态为 {status}。"
    else:
        delivery_status = "pending"
        summary = f"工作流 {spec_name} 进行中，当前已完成 {completed_steps}/{step_count} 个步骤。"
    return {
        "status": delivery_status,
        "channel": "workflow_view",
        "kind": "workflow.summary",
        "summary": summary,
        "workflow": workflow,
        "replay": replay,
        "resume": resume,
        "failure": failure,
    }


def _build_workflow_validation_summary(run_view: dict) -> dict:
    return {"risks": []}


def _build_workflow_preview_summary(run_view: dict) -> dict:
    timeline = run_view.get("timeline") or []
    steps = run_view.get("steps") or []
    return {
        "spec_name": run_view.get("spec_name", ""),
        "step_count": len(steps),
        "timeline_events": len(timeline),
        "status": str(run_view.get("status") or "pending"),
    }


def _build_workflow_evidence_records(run_view: dict) -> list[dict]:
    records: list[dict] = [
        {
            "kind": "request.input",
            "payload": {
                "spec_name": run_view.get("spec_name", ""),
                "goal_id": run_view.get("goal_id", ""),
                "spine_task_id": run_view.get("spine_task_id", ""),
                "steps": [
                    {
                        "id": step.get("id"),
                        "name": step.get("name"),
                        "status": step.get("status"),
                    }
                    for step in run_view.get("steps") or []
                ],
            },
        }
    ]
    delivery_summary = build_workflow_delivery_summary(run_view)
    for event in run_view.get("timeline") or []:
        kind = str(event.get("kind") or "").strip().lower()
        if kind == "approval_requested":
            records.append(
                {
                    "kind": "approval.requested",
                    "payload": {
                        "step_id": event.get("step_id"),
                        "detail": event.get("detail"),
                    },
                }
            )
        elif kind == "approved":
            records.append(
                {
                    "kind": "approval.approved",
                    "payload": {
                        "step_id": event.get("step_id"),
                        "actor": event.get("detail"),
                    },
                }
            )
        elif kind == "denied":
            records.append(
                {
                    "kind": "approval.denied",
                    "payload": {
                        "step_id": event.get("step_id"),
                        "actor": event.get("detail"),
                    },
                }
            )
    if str(run_view.get("status") or "") == "completed":
        records.append(
            {
                "kind": "result.final",
                "payload": {
                    "status": run_view.get("status"),
                    "completed_steps": sum(
                        1
                        for step in run_view.get("steps") or []
                        if step.get("status") == "succeeded"
                    ),
                    "step_count": len(run_view.get("steps") or []),
                },
            }
        )
    records.append({"kind": "delivery.generated", "payload": delivery_summary})
    return records


def _build_workflow_task_record(
    *,
    run_view: dict,
    owner_id: str,
    tenant_id: str,
) -> AgentTaskORM:
    timeline = run_view.get("timeline") or []
    steps = run_view.get("steps") or []
    status = str(run_view.get("status") or "pending")
    delivery_summary = build_workflow_delivery_summary(run_view)
    validation_summary = _build_workflow_validation_summary(run_view)
    preview_summary = _build_workflow_preview_summary(run_view)
    return AgentTaskORM(
        task_id=run_view["run_id"],
        run_id=run_view["run_id"],
        tenant_id=tenant_id,
        owner_id=owner_id,
        kind="workflow.run",
        status=status,
        backend="workflow",
        source="workflow",
        intent_type="workflow",
        route_source="planner",
        input_payload=json.dumps(
            {
                "spec_name": run_view.get("spec_name", ""),
                "goal_id": run_view.get("goal_id", ""),
                "spine_task_id": run_view.get("spine_task_id", ""),
                "steps": [
                    {
                        "id": step.get("id"),
                        "name": step.get("name"),
                        "depends_on": step.get("depends_on", []),
                    }
                    for step in steps
                ],
            },
            ensure_ascii=False,
        ),
        result_payload=json.dumps(
            {
                "status": status,
                "timeline": timeline,
            },
            ensure_ascii=False,
        ),
        validation_summary=json.dumps(validation_summary, ensure_ascii=False),
        delivery_summary=json.dumps(delivery_summary, ensure_ascii=False),
        preview_summary=json.dumps(preview_summary, ensure_ascii=False),
    )


async def _safe_get_runtime_task(session: AsyncSession, run_id: str) -> AgentTaskORM | None:
    try:
        return await session.get(AgentTaskORM, run_id)
    except ProgrammingError as exc:
        await session.rollback()
        if not _is_schema_mismatch(exc, "agent_tasks"):
            raise
        logger.warning("runtime_task_lookup_skipped", run_id=run_id, error=str(exc))
        return None
    except Exception as exc:
        if not _is_schema_mismatch(exc, "agent_tasks"):
            raise
        await session.rollback()
        logger.warning("runtime_task_lookup_skipped", run_id=run_id, error=str(exc))
        return None


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


async def _table_exists(session: AsyncSession, table_name: str) -> bool:
    def _inspect(sync_session) -> bool:
        bind = sync_session.connection()
        return bool(inspect(bind).has_table(table_name))

    try:
        return await session.run_sync(_inspect)
    except Exception as exc:
        if _is_schema_mismatch(exc, table_name):
            return False
        raise


async def _upsert_runtime_task_record(
    session: AsyncSession,
    *,
    run_view: dict,
    owner_id: str,
    tenant_id: str,
) -> None:
    if not await _table_exists(session, "agent_tasks"):
        logger.warning(
            "runtime_task_upsert_skipped", run_id=run_view.get("run_id"), error="table_missing"
        )
        return

    try:
        existing = await session.get(AgentTaskORM, run_view["run_id"])
        if existing is not None:
            existing_input = _decode_json_payload(existing.input_payload)
            run_view.setdefault("goal_id", str(existing_input.get("goal_id") or ""))
            run_view.setdefault("spine_task_id", str(existing_input.get("spine_task_id") or ""))
        task_record = _build_workflow_task_record(
            run_view=run_view,
            owner_id=owner_id,
            tenant_id=tenant_id,
        )
        if existing is None:
            session.add(task_record)
            return
        existing.run_id = task_record.run_id
        existing.tenant_id = task_record.tenant_id
        existing.owner_id = task_record.owner_id
        existing.kind = task_record.kind
        existing.status = task_record.status
        existing.backend = task_record.backend
        existing.source = task_record.source
        existing.intent_type = task_record.intent_type
        existing.route_source = task_record.route_source
        existing.input_payload = task_record.input_payload
        existing.result_payload = task_record.result_payload
        existing.delivery_summary = task_record.delivery_summary
        existing.preview_summary = task_record.preview_summary
    except ProgrammingError as exc:
        await session.rollback()
        if _is_schema_mismatch(exc, "agent_tasks"):
            logger.warning(
                "runtime_task_upsert_skipped", run_id=run_view.get("run_id"), error=str(exc)
            )
            return
        raise
    except Exception as exc:
        if _is_schema_mismatch(exc, "agent_tasks"):
            await session.rollback()
            logger.warning(
                "runtime_task_upsert_skipped", run_id=run_view.get("run_id"), error=str(exc)
            )
            return
        raise


async def _persist_workflow_view(session: AsyncSession, view: dict) -> None:
    try:
        await persist_workflow_run(session, view)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if _is_schema_mismatch(exc, "workflow_runs"):
            logger.warning(
                "workflow_view_persist_skipped", run_id=view.get("run_id"), error=str(exc)
            )
            return
        raise


async def _persist_workflow_runtime_and_view(
    session: AsyncSession,
    *,
    view: dict,
    owner_id: str,
    tenant_id: str,
) -> None:
    await _upsert_runtime_task_record(
        session,
        run_view=view,
        owner_id=owner_id,
        tenant_id=tenant_id,
    )
    await persist_evidence_bundle(
        session,
        tenant_id=tenant_id,
        run_id=str(view.get("run_id") or ""),
        task_id=str(view.get("run_id") or ""),
        records=_build_workflow_evidence_records(view),
    )
    await session.commit()
    await _persist_workflow_view(session, view)


async def _try_attach_spine_workflow_run(
    *,
    run_id: str,
    task_title: str,
    goal_id: str,
    spine_task_id: str,
    allow_legacy_title_fallback: bool,
    tenant_id: str,
) -> dict[str, str] | None:
    try:
        async with get_sessionmaker()() as attach_session:
            linkage = await attach_run_to_task(
                attach_session,
                tenant_id=tenant_id,
                run_id=run_id,
                spine_task_id=spine_task_id,
                goal_id=goal_id,
                task_title=task_title if allow_legacy_title_fallback else "",
                next_status="ready",
            )
            if linkage is None:
                return None
            await attach_session.commit()
            return linkage
    except Exception as exc:
        logger.warning(
            "attach_spine_workflow_run_failed",
            run_id=run_id,
            tenant_id=tenant_id,
            error=str(exc),
        )
        return None


@router.post("", summary="创建并启动工作流")
async def create_and_run(
    body: SpecIn,
    principal: Principal = Depends(require_permission("workflow", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    engine: WorkflowEngine = get_engine()
    try:
        resolved_goal_id, resolved_spine_task_id, strict_spine = await _resolve_spine_contract(
            principal=principal,
            goal_id=body.goal_id,
            spine_task_id=body.spine_task_id,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 422 if "必须同时提供" in message else 409
        raise HTTPException(status_code, message) from exc
    spec = _to_spec(body)
    run = engine.create_run(spec, principal)
    run = await engine.execute(run.run_id, principal)
    view = run.to_view()
    view["goal_id"] = resolved_goal_id
    view["spine_task_id"] = resolved_spine_task_id
    linkage = await _try_attach_spine_workflow_run(
        run_id=str(view.get("run_id") or ""),
        task_title=body.name,
        goal_id=resolved_goal_id,
        spine_task_id=resolved_spine_task_id,
        allow_legacy_title_fallback=not strict_spine,
        tenant_id=principal.tenant_id,
    )
    if strict_spine and linkage is None:
        raise HTTPException(status_code=409, detail="spine task 挂接失败")
    _apply_spine_provenance(view, linkage)
    await _persist_workflow_runtime_and_view(
        session,
        view=view,
        owner_id=principal.user_id,
        tenant_id=principal.tenant_id,
    )
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="workflow.run",
        resource="workflow",
        detail={"run_id": run.run_id, "status": run.status.value},
    )
    return view


@router.get("", summary="列出当前租户工作流（优先 DB 持久化记录）")
async def list_runs(
    principal: Principal = Depends(require_permission("workflow", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    engine = get_engine()
    # 优先返回 DB 持久化记录（跨重启不丢）；DB 空则回退内存
    db_runs = await load_workflow_runs(session, principal.tenant_id)
    if db_runs:
        return {"runs": db_runs, "source": "db"}
    runs = [r.to_view() for r in engine.list_runs(principal.tenant_id)]
    return {"runs": runs, "source": "memory"}


@router.get("/{run_id}", summary="查看工作流结构化视图（timeline）")
async def get_view(
    run_id: str,
    principal: Principal = Depends(require_permission("workflow", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    persisted_view = await load_workflow_run_by_id(session, principal.tenant_id, run_id)
    if persisted_view is not None:
        return persisted_view
    engine = get_engine()
    return engine.replay(run_id, principal)


@router.post("/{run_id}/approve/{step_id}", summary="审批通过")
async def approve(
    run_id: str,
    step_id: str,
    principal: Principal = Depends(require_permission("workflow", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    engine = get_engine()
    existing = await _safe_get_runtime_task(session, run_id)
    owner_id = (
        existing.owner_id if existing is not None and existing.owner_id else principal.user_id
    )
    run = await engine.approve(run_id, step_id, principal)
    view = run.to_view()
    if existing is not None:
        existing_input = _decode_json_payload(existing.input_payload)
        view["goal_id"] = str(existing_input.get("goal_id") or "")
        view["spine_task_id"] = str(existing_input.get("spine_task_id") or "")
    await _persist_workflow_runtime_and_view(
        session,
        view=view,
        owner_id=owner_id,
        tenant_id=principal.tenant_id,
    )
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="workflow.approve",
        resource="workflow",
        detail={"run_id": run_id, "step_id": step_id},
    )
    return view


@router.post("/{run_id}/deny/{step_id}", summary="审批拒绝")
async def deny(
    run_id: str,
    step_id: str,
    principal: Principal = Depends(require_permission("workflow", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    engine = get_engine()
    existing = await _safe_get_runtime_task(session, run_id)
    owner_id = (
        existing.owner_id if existing is not None and existing.owner_id else principal.user_id
    )
    run = await engine.deny(run_id, step_id, principal)
    view = run.to_view()
    if existing is not None:
        existing_input = _decode_json_payload(existing.input_payload)
        view["goal_id"] = str(existing_input.get("goal_id") or "")
        view["spine_task_id"] = str(existing_input.get("spine_task_id") or "")
    await _persist_workflow_runtime_and_view(
        session,
        view=view,
        owner_id=owner_id,
        tenant_id=principal.tenant_id,
    )
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="workflow.deny",
        resource="workflow",
        detail={"run_id": run_id, "step_id": step_id},
    )
    return view
