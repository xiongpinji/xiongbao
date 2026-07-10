"""Agent 路由：运行 agent 任务、列出角色。

安全：execute 需 agent:execute 权限；运行结果写审计链；租户来自 principal，
调用方无法伪造（不从 body 取 tenant_id）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.agents import get_role_registry
from xagent.core.orchestration import run_agent
from xagent.domains.billing import get_billing_service
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session, get_sessionmaker
from xagent.infra.logging import get_logger
from xagent.infra.repos.billing import persist_billing_record
from xagent.infra.repos.evidence import persist_evidence_bundle
from xagent.infra.repos.spine import attach_run_to_task
from xagent.worker.celery_app import persist_agent_task_record_in_session

router = APIRouter(prefix="/agents", tags=["agents"])
logger = get_logger("xagent.api.agents")


class RunRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="任务目标")
    role: str | None = Field(None, description="指定角色名；不指定则按能力匹配")
    capabilities: list[str] = Field(default_factory=list, description="任务所需能力标签")
    model: str | None = None


def _build_input_payload(body: RunRequest) -> dict:
    return {
        "goal": body.goal,
        "role": body.role,
        "capabilities": list(body.capabilities),
        "model": body.model,
    }


def _build_result_summary(result: dict) -> dict:
    final_answer = str(result.get("final_answer") or "").strip()
    steps_value = result.get("steps")
    steps_count = steps_value if isinstance(steps_value, int) else len(steps_value or [])
    return {
        "status": "succeeded",
        "run_id": str(result.get("run_id") or ""),
        "role": str(result.get("role") or result.get("role_name") or ""),
        "steps_count": steps_count,
        "final_answer": final_answer[:400],
    }


def _build_delivery_summary(run_id: str, result: dict) -> dict:
    result_summary = _build_result_summary(result)
    return {
        "status": "ready",
        "channel": "task_runtime",
        "kind": "agent.run",
        "summary": (
            f"Agent 已完成 {result_summary['steps_count']} 个步骤，产出最终答复。"
            if result_summary["steps_count"]
            else "Agent 已完成运行并产出最终答复。"
        ),
        "result": result_summary,
        "replay": {
            "mode": "task_detail",
            "label": "查看后台任务",
            "run_id": run_id,
            "task_id": run_id,
            "api_path": f"/api/v1/tasks/{run_id}",
            "console_path": f"/runs/{run_id}",
        },
        "resume": None,
        "artifacts": [],
        "validation": {"risks": []},
        "risks": [],
    }


def _build_failure_result_summary(*, run_id: str, error: str, role: str | None) -> dict:
    return {
        "status": "failed",
        "run_id": run_id,
        "role": str(role or ""),
        "steps_count": 0,
        "final_answer": "",
        "error": error,
    }


def _build_failure_delivery_summary(*, run_id: str, result_summary: dict) -> dict:
    error_text = str(result_summary.get("error") or "").strip()
    return {
        "status": "blocked",
        "channel": "task_runtime",
        "kind": "agent.run",
        "summary": f"Agent 运行失败，当前交付已阻塞：{error_text}",
        "result": result_summary,
        "blocking_step": "agent.run",
        "suggested_repair_actions": ["检查错误信息并重试该任务"],
        "escalation_path": "agent_support",
        "replay": {
            "mode": "task_detail",
            "label": "查看后台任务",
            "run_id": run_id,
            "task_id": run_id,
            "api_path": f"/api/v1/tasks/{run_id}",
            "console_path": f"/runs/{run_id}",
        },
        "resume": {
            "mode": "task_follow",
            "label": "继续查看后台任务",
            "run_id": run_id,
            "task_id": run_id,
            "status": "failed",
            "api_path": f"/api/v1/tasks/{run_id}",
            "console_path": f"/runs/{run_id}",
        },
        "artifacts": [],
        "validation": {"risks": []},
        "risks": [error_text] if error_text else [],
    }


def _build_commit_evidence(result: dict) -> dict | None:
    events = result.get("events")
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        tool_name = str(event.get("tool") or "")
        content = event.get("content")
        if tool_name != "git_commit":
            continue
        payload = {"tool": tool_name, "content": content}
        if isinstance(content, dict):
            payload = dict(content)
            payload.setdefault("tool", tool_name)
        elif isinstance(content, str) and content.strip():
            payload["summary"] = content.strip()[:400]
        return {"kind": "commit.last", "payload": payload}
    return None


def _is_runtime_persistence_schema_mismatch(exc: Exception) -> bool:
    parts = [str(exc)]
    for attr in ("orig", "statement", "params"):
        value = getattr(exc, attr, None)
        if value is not None:
            parts.append(str(value))
    lowered = " ".join(parts).lower()
    return any(table in lowered for table in ("agent_tasks", "evidence")) and any(
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


async def _try_attach_spine_run(
    *,
    run_id: str,
    task_title: str,
    tenant_id: str,
) -> dict[str, str] | None:
    try:
        async with get_sessionmaker()() as session:
            linkage = await attach_run_to_task(
                session,
                tenant_id=tenant_id,
                task_title=task_title,
                run_id=run_id,
            )
            if linkage is None:
                return None
            await session.commit()
            return linkage
    except Exception as exc:
        logger.warning(
            "attach_spine_agent_run_failed",
            run_id=run_id,
            tenant_id=tenant_id,
            error=str(exc),
        )
        return None


@router.get("/roles", summary="列出可用 agent 角色")
async def list_roles(
    principal: Principal = Depends(require_permission("agent", "read")),
) -> dict:
    roles = get_role_registry().all()
    return {
        "roles": [
            {
                "name": r.name,
                "description": r.description,
                "capabilities": sorted(r.capabilities),
            }
            for r in roles
        ]
    }


@router.post("/run", summary="运行一次 agent 任务")
async def run(
    body: RunRequest,
    principal: Principal = Depends(require_permission("agent", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # 计费：配额校验 + 用量累计
    billing = get_billing_service()
    try:
        billing.check_and_consume(
            principal.tenant_id,
            actor=principal.user_id,
            action="agent.run",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        ) from exc

    run_id = uuid.uuid4().hex
    input_payload = _build_input_payload(body)
    started_at = datetime.now(UTC)

    try:
        result = await run_agent(
            body.goal,
            principal=principal,
            role_name=body.role,
            capabilities=set(body.capabilities) or None,
            model=body.model,
            session=session,
            run_id=run_id,
        )
        await _try_attach_spine_run(
            run_id=run_id,
            task_title=body.goal,
            tenant_id=principal.tenant_id,
        )
        result_payload = result.to_dict()
        delivery_summary = _build_delivery_summary(result.run_id, result_payload)
        validation_summary = {"risks": []}
        preview_summary = {
            "final_answer": str(result_payload.get("final_answer") or "")[:160],
            "steps_count": _build_result_summary(result_payload)["steps_count"],
        }
        evidence_records = [
            {"kind": "request.input", "payload": input_payload},
            {"kind": "result.final", "payload": _build_result_summary(result_payload)},
            {"kind": "delivery.generated", "payload": delivery_summary},
        ]
        commit_evidence = _build_commit_evidence(result_payload)
        if commit_evidence is not None:
            evidence_records.append(commit_evidence)

        await persist_agent_task_record_in_session(
            session,
            task_id=result.run_id,
            run_id=result.run_id,
            tenant_id=principal.tenant_id,
            owner_id=principal.user_id,
            kind="agent.run",
            backend="agent",
            status="succeeded",
            input_payload=input_payload,
            result_payload=result_payload,
            delivery_summary=delivery_summary,
            validation_summary=validation_summary,
            preview_summary=preview_summary,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        try:
            await persist_evidence_bundle(
                session,
                tenant_id=principal.tenant_id,
                run_id=result.run_id,
                task_id=result.run_id,
                records=evidence_records,
            )
            await session.commit()
        except Exception as evidence_exc:
            await session.rollback()
            if _is_runtime_persistence_schema_mismatch(evidence_exc):
                await persist_agent_task_record_in_session(
                    session,
                    task_id=result.run_id,
                    run_id=result.run_id,
                    tenant_id=principal.tenant_id,
                    owner_id=principal.user_id,
                    kind="agent.run",
                    backend="agent",
                    status="succeeded",
                    input_payload=input_payload,
                    result_payload=result_payload,
                    delivery_summary=delivery_summary,
                    validation_summary=validation_summary,
                    preview_summary=preview_summary,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                await session.commit()
            else:
                raise
    except Exception as exc:
        await session.rollback()
        if _is_runtime_persistence_schema_mismatch(exc):
            result_payload = result.to_dict()
        else:
            failure_error = str(exc)
            failed_result = _build_failure_result_summary(
                run_id=run_id,
                error=failure_error,
                role=body.role,
            )
            failed_delivery = _build_failure_delivery_summary(
                run_id=run_id,
                result_summary=failed_result,
            )
            failure_evidence = [
                {"kind": "request.input", "payload": input_payload},
                {"kind": "failure.evidence", "payload": {"error": failure_error, "run_id": run_id}},
                {"kind": "delivery.generated", "payload": failed_delivery},
            ]
            try:
                await persist_agent_task_record_in_session(
                    session,
                    task_id=run_id,
                    run_id=run_id,
                    tenant_id=principal.tenant_id,
                    owner_id=principal.user_id,
                    kind="agent.run",
                    backend="agent",
                    status="failed",
                    input_payload=input_payload,
                    result_payload=failed_result,
                    error=failure_error,
                    delivery_summary=failed_delivery,
                    validation_summary={"risks": []},
                    preview_summary={"error": failure_error[:160], "steps_count": 0},
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                await persist_evidence_bundle(
                    session,
                    tenant_id=principal.tenant_id,
                    run_id=run_id,
                    task_id=run_id,
                    records=failure_evidence,
                )
                await session.commit()
            except Exception:
                await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"run_id": run_id, "error": failure_error},
            ) from exc
    # 账单落库（best-effort）
    await persist_billing_record(
        session,
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="agent.run",
        cost=0.0,
        tokens=result.steps,
        detail={"run_id": result.run_id, "role": result.role_name},
    )
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="agent.run",
        resource="agent",
        detail={"run_id": result.run_id, "role": result.role_name, "steps": result.steps},
    )
    return result_payload
