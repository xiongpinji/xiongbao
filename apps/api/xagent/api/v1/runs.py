"""统一 Runtime runs 聚合路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.api.v1.workflows import build_workflow_replay_pointer, build_workflow_resume_pointer
from xagent.core.runtime.service import get_runtime_run_detail
from xagent.enterprise.auth.dependencies import get_principal
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.rbac import AccessRequest, authorize
from xagent.infra.db import get_session

router = APIRouter(prefix="/runs", tags=["runs"])


def _can_read_runtime_detail(principal: Principal, detail: dict) -> bool:
    workflow = detail.get("workflow")
    task = detail.get("task") or {}
    intent_type = str(task.get("intent_type") or "").strip().lower()
    source = str(task.get("source") or "").strip().lower()

    if workflow is not None or intent_type == "workflow" or source == "workflow":
        return authorize(principal, AccessRequest(resource="workflow", action="read"))
    if intent_type == "creative":
        return authorize(principal, AccessRequest(resource="creative", action="read"))
    return authorize(principal, AccessRequest(resource="agent", action="read"))


def _normalize_risks(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    risks: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            risks.append(text)
    return risks


def _enrich_validation(detail: dict) -> dict:
    validation = detail.get("validation")
    merged = validation.copy() if isinstance(validation, dict) else {}
    merged["risks"] = _normalize_risks(merged.get("risks"))
    return merged


def _enrich_delivery(detail: dict) -> dict:
    delivery = detail.get("delivery")
    workflow = detail.get("workflow")
    merged = delivery.copy() if isinstance(delivery, dict) else {}
    merged["risks"] = _normalize_risks(merged.get("risks"))
    if not isinstance(workflow, dict):
        return merged
    if "replay" not in merged:
        merged["replay"] = build_workflow_replay_pointer(
            str(detail.get("run_id") or workflow.get("run_id") or "")
        )
    if "resume" not in merged:
        merged["resume"] = build_workflow_resume_pointer(workflow)
    return merged


def _enrich_spine(detail: dict) -> dict[str, str]:
    spine = detail.get("spine")
    if not isinstance(spine, dict):
        return {"goal_id": "", "initiative_id": "", "spine_task_id": ""}
    return {
        "goal_id": str(spine.get("goal_id") or ""),
        "initiative_id": str(spine.get("initiative_id") or ""),
        "spine_task_id": str(spine.get("spine_task_id") or ""),
    }


@router.get("/{run_id}", summary="查看统一 Runtime 聚合视图")
async def get_run(
    run_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    detail = await get_runtime_run_detail(
        session,
        run_id=run_id,
        tenant_id=principal.tenant_id,
    )
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "运行不存在或无权访问")
    detail["validation"] = _enrich_validation(detail)
    detail["delivery"] = _enrich_delivery(detail)
    detail["spine"] = _enrich_spine(detail)
    if not _can_read_runtime_detail(principal, detail):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该运行")
    return detail
