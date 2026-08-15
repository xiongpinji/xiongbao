"""短剧工厂路由：一句话→草稿、草稿审阅、质量门。强鉴权 + RBAC + 租户隔离。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.core.orchestration.task_view import build_task_view
from xagent.domains.creative_studio import build_draft_from_brief
from xagent.domains.creative_studio import persistence as creative_persistence
from xagent.domains.creative_studio.editor.tools import get_timeline
from xagent.domains.creative_studio.media import (
    GenerationMode,
    GenerationRequest,
    MediaKind,
    get_media_registry,
)
from xagent.domains.creative_studio.pipeline import produce_short_drama
from xagent.domains.creative_studio.producer import generate_storyboard
from xagent.domains.creative_studio.quality import run_gates
from xagent.domains.creative_studio.storyboard import Storyboard
from xagent.enterprise.audit import get_audit_log
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_session
from xagent.infra.logging import get_logger
from xagent.infra.models.agent_task import AgentTaskORM
from xagent.infra.repos.artifact import (
    build_artifact_view,
    infer_artifact_content_type,
    upsert_artifact_record,
)
from xagent.infra.repos.evidence import persist_evidence_bundle

router = APIRouter(prefix="/creative-studio", tags=["creative-studio"])
logger = get_logger("xagent.api.creative_studio")

# 进程内草稿存储（Phase 5 已落库 creative_persistence，此处作内存缓存）；按租户隔离
_drafts: dict[str, dict] = {}
# 进程内成片产物存储（已落库，此处作内存缓存）；按租户隔离
_productions: dict[str, dict] = {}
# 媒体任务租户映射（用于按租户拉取 task 状态；已落库）
_media_task_tenants: dict[str, str] = {}
# unified runtime 过渡态：creative 入口补充最小 run/task 映射
_media_runtime_tasks: dict[str, dict] = {}
# unified runtime 过渡态：creative produce 结果按 run_id 暴露
_production_runtime_runs: dict[str, dict] = {}

# 持久化恢复标记：每进程首次读时从 DB 水合一次（重启恢复语义）；
# 测试清空进程内 dict 后不重新水合，保证用例间隔离。
_persistence_hydrated = False


async def _hydrate_from_persistence() -> None:
    """首次访问时从 DB 恢复草稿/产物/媒体任务租户映射到进程内缓存。"""
    global _persistence_hydrated
    if _persistence_hydrated:
        return
    _persistence_hydrated = True
    try:
        for draft_id, doc in (await creative_persistence.load_all_drafts()).items():
            _drafts.setdefault(draft_id, doc)
        for storyboard_id, doc in (await creative_persistence.load_all_productions()).items():
            _productions.setdefault(storyboard_id, doc)
        for task_id, tenant_id in (
            await creative_persistence.load_all_media_task_tenants()
        ).items():
            _media_task_tenants.setdefault(task_id, tenant_id)
    except Exception as exc:  # 持久化恢复失败不影响主流程
        logger.warning("creative_hydrate_failed", error=str(exc))


class BriefIn(BaseModel):
    brief: str = Field(..., min_length=1)
    genre: str = "逆袭"
    platform: str = "抖音"
    target_duration_seconds: float = 60.0


class ReviewIn(BaseModel):
    approved: bool
    comment: str = ""


@router.post("/workflow-draft", summary="一句话生成待审核工作流草稿")
async def create_draft(
    body: BriefIn,
    principal: Principal = Depends(require_permission("creative", "write")),
) -> dict:
    draft = build_draft_from_brief(
        body.brief,
        genre=body.genre,
        platform=body.platform,
        target_duration_seconds=body.target_duration_seconds,
    )
    doc = draft.to_dict()
    doc["tenant_id"] = principal.tenant_id
    doc["owner"] = principal.user_id
    _drafts[draft.draft_id] = doc
    await creative_persistence.save_draft(doc)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.draft",
        resource="creative",
        detail={"draft_id": draft.draft_id, "genre": body.genre},
    )
    return doc


@router.post("/workflow-draft/{draft_id}/review", summary="审核草稿（通过/驳回）")
async def review_draft(
    draft_id: str,
    body: ReviewIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
) -> dict:
    await _hydrate_from_persistence()
    doc = _drafts.get(draft_id)
    if doc is None or doc.get("tenant_id") != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "草稿不存在或无权访问")
    doc["status"] = "approved" if body.approved else "rejected"
    doc["review_comment"] = body.comment
    await creative_persistence.save_draft(doc)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.review",
        resource="creative",
        detail={"draft_id": draft_id, "approved": body.approved},
    )
    return doc


@router.get("/workflow-drafts", summary="列出当前租户草稿")
async def list_drafts(
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    await _hydrate_from_persistence()
    items = [d for d in _drafts.values() if d.get("tenant_id") == principal.tenant_id]
    return {"drafts": items}


@router.post("/quality-gates", summary="对故事板运行质量门")
async def quality_gates(
    sb: Storyboard,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    gates = run_gates(sb)
    return {
        "all_passed": all(g.passed for g in gates),
        "gates": [g.model_dump() for g in gates],
    }


@router.post("/storyboard/generate", summary="LLM 生成结构化故事板")
async def gen_storyboard(
    body: BriefIn,
    principal: Principal = Depends(require_permission("creative", "write")),
) -> dict:
    sb = await generate_storyboard(
        body.brief,
        genre=body.genre,
        platform=body.platform,
        target_duration_seconds=body.target_duration_seconds,
    )
    gates = run_gates(sb)
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.storyboard",
        resource="creative",
        detail={"shots": len(sb.shots), "all_passed": all(g.passed for g in gates)},
    )
    return {
        "storyboard": sb.model_dump(),
        "quality_gates": {
            "all_passed": all(g.passed for g in gates),
            "gates": [g.model_dump() for g in gates],
        },
    }


class MediaGenIn(BaseModel):
    kind: str = "image"  # image | video
    prompt: str = Field(..., min_length=1)
    mode: str = "text_to_image"  # text_to_image|image_to_image|text_to_video|image_to_video
    model_id: str | None = None
    reference_images: list[str] = Field(default_factory=list)
    duration_seconds: float | None = None
    resolution: str | None = None
    negative_prompt: str = ""
    seed: int | None = None
    # 节点 settings 透传：sampler/scheduler/steps/cfg/batch/strategy 等
    mode_settings: dict = Field(default_factory=dict)
    wait: bool = False  # True 则轮询直到完成


def _build_creative_task_view(
    *,
    task_id: str,
    tenant_id: str,
    owner_id: str,
    kind: str,
    backend: str,
    status: str,
    input_payload: dict,
    result: dict,
    error: str = "",
) -> dict:
    return build_task_view(
        task_id=task_id,
        run_id=task_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        kind=kind,
        backend=backend,
        status=status,
        input_payload=deepcopy(input_payload),
        result=deepcopy(result),
        error=error,
        source="task",
        intent_type="creative",
        route_source="fallback",
    )


def _build_media_artifacts(
    *,
    task_id: str,
    tenant_id: str,
    kind: str,
    provider: str,
    prompt: str,
    mode: str,
    outputs: list[str],
) -> list[dict[str, Any]]:
    media_kind = kind.split(".")[-1] if kind else "asset"
    artifacts: list[dict[str, Any]] = []
    for idx, uri in enumerate(outputs, start=1):
        label = f"{media_kind}-{idx}"
        artifacts.append(
            build_artifact_view(
                artifact_id=task_id if idx == 1 else f"{task_id}-{idx}",
                run_id=task_id,
                task_id=task_id,
                tenant_id=tenant_id,
                kind=kind,
                name=f"{media_kind}-output-{idx}",
                uri=uri,
                content_type=infer_artifact_content_type(uri, media_kind=media_kind),
                delivery_summary={
                    "label": label,
                    "media_kind": media_kind,
                    "provider": provider,
                },
                preview_summary={"prompt": prompt, "mode": mode},
            )
        )
    return artifacts


def _build_media_delivery_summary(
    *,
    kind: str,
    provider: str,
    outputs: list[str],
) -> dict[str, Any]:
    media_kind = kind.split(".")[-1] if kind else "asset"
    has_outputs = bool(outputs)
    return {
        "status": "ready" if has_outputs else "pending",
        "channel": "media_outputs",
        "kind": "creative.media",
        "summary": (
            f"已生成 {len(outputs)} 个{media_kind} 产物，可直接用于交付。"
            if has_outputs
            else f"{media_kind} 产物尚未生成，等待媒体任务完成。"
        ),
        "outputs": [
            {
                "label": f"{media_kind}-{idx}",
                "uri": uri,
                "media_kind": media_kind,
            }
            for idx, uri in enumerate(outputs, start=1)
        ],
        "provider": provider,
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


def _attach_delivery_bundle(
    *,
    delivery: dict[str, Any],
    artifacts: list[dict[str, Any]],
    validation: dict[str, Any],
    replay: dict[str, Any] | None = None,
    resume: dict[str, Any] | None = None,
    extra_risks: list[str] | None = None,
) -> dict[str, Any]:
    bundled = deepcopy(delivery)
    bundled["artifacts"] = _build_delivery_artifact_projection(artifacts)
    bundled["validation"] = deepcopy(validation or {"risks": []})
    bundled["replay"] = deepcopy(replay)
    bundled["resume"] = deepcopy(resume)
    risks = [str(item).strip() for item in (bundled.get("risks") or []) if str(item).strip()]
    validation_risks = [
        str(item).strip() for item in ((validation or {}).get("risks") or []) if str(item).strip()
    ]
    extra = [str(item).strip() for item in (extra_risks or []) if str(item).strip()]
    merged_risks: list[str] = []
    for item in [*risks, *validation_risks, *extra]:
        if item and item not in merged_risks:
            merged_risks.append(item)
    bundled["risks"] = merged_risks
    return bundled


def _build_media_task_state(
    *,
    task_id: str,
    tenant_id: str,
    owner_id: str,
    kind: str,
    provider: str,
    status: str,
    input_payload: dict[str, Any],
    outputs: list[str],
    error: str,
) -> tuple[
    dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, Any]]
]:
    runtime_task = _build_creative_task_view(
        task_id=task_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        kind=kind,
        backend=provider,
        status=status,
        input_payload=input_payload,
        result={"outputs": list(outputs)},
        error=error,
    )
    artifacts = _build_media_artifacts(
        task_id=task_id,
        tenant_id=tenant_id,
        kind=kind,
        provider=provider,
        prompt=str(input_payload.get("prompt") or ""),
        mode=str(input_payload.get("mode") or ""),
        outputs=list(outputs),
    )
    validation = {"risks": []}
    delivery = _attach_delivery_bundle(
        delivery=_build_media_delivery_summary(
            kind=kind,
            provider=provider,
            outputs=list(outputs),
        ),
        artifacts=artifacts,
        validation=validation,
    )
    preview_summary = {
        "prompt": str(input_payload.get("prompt") or ""),
        "mode": str(input_payload.get("mode") or ""),
        "provider": provider,
    }
    evidence = [
        {"kind": "request.input", "payload": deepcopy(input_payload)},
        {
            "kind": "media.poll_result" if outputs else "media.request",
            "payload": {
                "status": status,
                "provider": provider,
                "outputs": list(outputs),
                "error": error,
            },
        },
        {"kind": "delivery.generated", "payload": deepcopy(delivery)},
    ]
    return runtime_task, artifacts, delivery, preview_summary, evidence


def _restore_media_runtime_view(
    *,
    task_id: str,
    tenant_id: str,
    owner_id: str,
    kind: str,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": task_id,
        "tenant_id": tenant_id,
        "task": {
            "task_id": task_id,
            "run_id": task_id,
            "tenant_id": tenant_id,
            "owner_id": owner_id,
            "kind": kind,
            "backend": "",
            "status": "pending",
            "source": "task",
            "intent_type": "creative",
            "route_source": "fallback",
            "input": deepcopy(input_payload),
            "result": {},
            "error": "",
            "created_at": None,
            "started_at": None,
            "finished_at": None,
            "updated_at": None,
        },
        "workflow": None,
        "evidence": [
            {"kind": "request.input", "payload": deepcopy(input_payload)},
        ],
        "artifacts": [],
        "validation": {"risks": []},
        "delivery": {
            "status": "pending",
            "channel": "media_outputs",
            "kind": "creative.media",
            "summary": "媒体任务已提交，等待轮询结果。",
            "outputs": [],
            "provider": "",
            "artifacts": [],
            "validation": {"risks": []},
            "replay": None,
            "resume": None,
            "risks": [],
        },
        "related_tasks": [],
    }


def _build_creative_task_record(
    *,
    task_view: dict[str, Any],
    validation: dict[str, Any],
    delivery: dict[str, Any],
    preview_summary: dict[str, Any],
) -> AgentTaskORM:
    return AgentTaskORM(
        task_id=str(task_view["task_id"]),
        run_id=str(task_view["run_id"]),
        tenant_id=str(task_view["tenant_id"]),
        owner_id=str(task_view.get("owner_id") or ""),
        kind=str(task_view.get("kind") or "creative.task"),
        status=str(task_view.get("status") or "pending"),
        backend=str(task_view.get("backend") or ""),
        source=str(task_view.get("source") or "task"),
        intent_type=str(task_view.get("intent_type") or "creative"),
        route_source=str(task_view.get("route_source") or "fallback"),
        input_payload=json.dumps(task_view.get("input") or {}, ensure_ascii=False),
        result_payload=json.dumps(task_view.get("result") or {}, ensure_ascii=False),
        error=str(task_view.get("error") or ""),
        validation_summary=json.dumps(validation or {}, ensure_ascii=False),
        delivery_summary=json.dumps(delivery or {}, ensure_ascii=False),
        preview_summary=json.dumps(preview_summary or {}, ensure_ascii=False),
    )


def _is_missing_runtime_table_error(exc: Exception, table_name: str) -> bool:
    parts = [str(exc)]
    orig = getattr(exc, "orig", None)
    if orig is not None:
        parts.append(str(orig))
    statement = getattr(exc, "statement", None)
    if statement is not None:
        parts.append(str(statement))
    params = getattr(exc, "params", None)
    if params is not None:
        parts.append(str(params))
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
        if _is_missing_runtime_table_error(exc, table_name):
            return False
        raise


def _decode_json_payload(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def _load_persisted_media_runtime_view(
    session: AsyncSession,
    *,
    task_id: str,
    tenant_id: str,
) -> dict[str, Any] | None:
    try:
        row = await session.get(AgentTaskORM, task_id)
    except Exception as exc:
        if _is_missing_runtime_table_error(exc, "agent_tasks"):
            return None
        raise
    if row is None or row.tenant_id != tenant_id:
        return None
    task_view = _build_creative_task_view(
        task_id=row.task_id,
        tenant_id=row.tenant_id,
        owner_id=row.owner_id,
        kind=row.kind,
        backend=row.backend,
        status=row.status,
        input_payload=_decode_json_payload(row.input_payload),
        result=_decode_json_payload(row.result_payload),
        error=row.error,
    )
    return {
        "run_id": row.run_id,
        "tenant_id": row.tenant_id,
        "task": task_view,
        "workflow": None,
        "evidence": [],
        "artifacts": [],
        "validation": _decode_json_payload(row.validation_summary),
        "delivery": _decode_json_payload(row.delivery_summary),
        "related_tasks": [],
    }


async def _upsert_creative_runtime_task(
    session: AsyncSession,
    *,
    task_view: dict[str, Any],
    validation: dict[str, Any],
    delivery: dict[str, Any],
    preview_summary: dict[str, Any],
) -> None:
    task_record = _build_creative_task_record(
        task_view=task_view,
        validation=validation,
        delivery=delivery,
        preview_summary=preview_summary,
    )
    existing = await session.get(AgentTaskORM, task_record.task_id)
    if existing is None:
        session.add(task_record)
    else:
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
        existing.error = task_record.error
        existing.validation_summary = task_record.validation_summary
        existing.delivery_summary = task_record.delivery_summary
        existing.preview_summary = task_record.preview_summary


async def _upsert_creative_artifacts(
    session: AsyncSession,
    *,
    artifacts: list[dict[str, Any]],
) -> None:
    for artifact in artifacts:
        await upsert_artifact_record(session, artifact_view=artifact)


async def _persist_creative_runtime_state(
    session: AsyncSession,
    *,
    task_view: dict[str, Any],
    validation: dict[str, Any],
    delivery: dict[str, Any],
    preview_summary: dict[str, Any],
    artifacts: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> None:
    if not await _table_exists(session, "agent_tasks"):
        logger.warning(
            "creative_runtime_persist_skipped",
            task_id=task_view.get("task_id"),
            table="agent_tasks",
            error="table_missing",
        )
        return

    try:
        await _upsert_creative_runtime_task(
            session,
            task_view=task_view,
            validation=validation,
            delivery=delivery,
            preview_summary=preview_summary,
        )
        await persist_evidence_bundle(
            session,
            tenant_id=str(task_view.get("tenant_id") or ""),
            run_id=str(task_view.get("run_id") or task_view.get("task_id") or ""),
            task_id=str(task_view.get("task_id") or ""),
            records=evidence,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if _is_missing_runtime_table_error(exc, "agent_tasks"):
            logger.warning(
                "creative_runtime_persist_skipped",
                task_id=task_view.get("task_id"),
                table="agent_tasks",
                error=str(exc),
            )
            return
        raise

    if artifacts and not await _table_exists(session, "artifacts"):
        logger.warning(
            "creative_runtime_persist_skipped",
            task_id=task_view.get("task_id"),
            table="artifacts",
            error="table_missing",
        )
        return

    if not artifacts:
        return

    try:
        await _upsert_creative_artifacts(session, artifacts=artifacts)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if _is_missing_runtime_table_error(exc, "artifacts"):
            logger.warning(
                "creative_runtime_persist_skipped",
                task_id=task_view.get("task_id"),
                table="artifacts",
                error=str(exc),
            )
            return
        raise


def _build_production_artifacts(
    *,
    run_id: str,
    tenant_id: str,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    title = str(result.get("title") or run_id)
    for shot in result.get("shots") or []:
        shot_id = str(shot.get("shot_id") or "shot")
        for media_kind, field in (("image", "image_outputs"), ("video", "video_outputs")):
            for idx, uri in enumerate(shot.get(field) or [], start=1):
                artifacts.append(
                    build_artifact_view(
                        artifact_id=f"{run_id}-{shot_id}-{media_kind}-{idx}",
                        run_id=run_id,
                        task_id=run_id,
                        tenant_id=tenant_id,
                        kind="creative.asset",
                        name=f"{title}-{shot_id}-{media_kind}-{idx}",
                        uri=uri,
                        content_type=infer_artifact_content_type(uri, media_kind=media_kind),
                        delivery_summary={
                            "storyboard_id": run_id,
                            "shot_id": shot_id,
                            "media_kind": media_kind,
                            "index": idx,
                        },
                        preview_summary={
                            "title": title,
                            "scene": shot.get("scene", ""),
                            "plot_purpose": shot.get("plot_purpose", ""),
                        },
                    )
                )
    return artifacts


def _build_production_validation_summary(result: dict[str, Any]) -> dict[str, Any]:
    quality_gates = deepcopy(result.get("quality_gates") or [])
    risks = [
        str(gate.get("detail") or "").strip()
        for gate in quality_gates
        if isinstance(gate, dict)
        and not gate.get("passed")
        and str(gate.get("detail") or "").strip()
    ]
    return {
        "all_passed": bool(result.get("quality_passed")),
        "gates": quality_gates,
        "risks": risks,
    }


def _build_production_failure_bundle(
    *,
    result: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any] | None:
    production_status = str(result.get("status") or "pending")
    if production_status not in {"partial", "failed"}:
        return None

    failed_shot = next(
        (
            shot
            for shot in result.get("shots") or []
            if str(shot.get("image_error") or "").strip()
            or str(shot.get("video_error") or "").strip()
        ),
        None,
    )
    blocking_step = str((failed_shot or {}).get("shot_id") or "creative_production").strip()
    step_name = str((failed_shot or {}).get("scene") or "").strip() or None
    shot_error = str(
        (failed_shot or {}).get("video_error") or (failed_shot or {}).get("image_error") or ""
    ).strip()
    validation_risks = [
        str(item).strip() for item in (validation.get("risks") or []) if str(item).strip()
    ]
    gate_failures = [
        {
            "name": str(gate.get("name") or "").strip(),
            "detail": str(gate.get("detail") or "").strip(),
        }
        for gate in result.get("quality_gates") or []
        if isinstance(gate, dict) and not gate.get("passed")
    ]
    reason = shot_error or validation_risks[0] if validation_risks else shot_error
    if not reason:
        reason = "部分镜头生成失败，请检查质量门与镜头产出。"
    message = (
        f"镜头 {blocking_step} 生成失败，当前短剧产出部分阻塞。"
        if production_status == "partial"
        else f"镜头 {blocking_step} 生成失败，当前短剧产出失败。"
    )

    details: dict[str, Any] = {
        "workflow_status": production_status,
        "quality_gate_failures": gate_failures,
    }
    if shot_error:
        details["shot_error"] = shot_error
    if validation_risks:
        details["validation_risks"] = validation_risks

    return {
        "code": production_status,
        "source": "creative",
        "message": message,
        "blocking_step": blocking_step,
        "step_name": step_name,
        "retryable": True,
        "recommended_action": "检查失败镜头与质量门后重新生成短剧产物",
        "details": details,
        "reason": reason,
    }


def _build_production_delivery_summary(
    *,
    result: dict[str, Any],
    artifacts: list[dict[str, Any]],
    validation: dict[str, Any],
) -> dict[str, Any]:
    shot_count = len(result.get("shots") or [])
    output_count = len(artifacts)
    production_status = str(result.get("status") or "pending")
    if production_status == "produced":
        delivery_status = "ready"
        summary = f"短剧已生成，{shot_count} 个镜头，共 {output_count} 个媒体产物。"
    elif production_status == "partial":
        delivery_status = "blocked"
        summary = f"短剧产出部分完成，{shot_count} 个镜头，共 {output_count} 个媒体产物。"
    elif production_status == "failed":
        delivery_status = "blocked"
        summary = f"短剧产出失败，{shot_count} 个镜头，共 {output_count} 个媒体产物。"
    else:
        delivery_status = "pending"
        summary = f"短剧产出进行中，{shot_count} 个镜头，共 {output_count} 个媒体产物。"
    return {
        "status": delivery_status,
        "channel": "creative_production",
        "kind": "creative.production",
        "summary": summary,
        "storyboard_id": result.get("storyboard_id"),
        "title": result.get("title", ""),
        "timeline_id": result.get("timeline_id"),
        "quality_passed": bool(result.get("quality_passed")),
        "output_count": output_count,
        "failure": _build_production_failure_bundle(result=result, validation=validation),
    }


def _build_production_evidence(
    *,
    input_payload: dict[str, Any],
    result: dict[str, Any],
    validation: dict[str, Any],
    delivery: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {"kind": "request.input", "payload": deepcopy(input_payload)},
        {
            "kind": "production.result",
            "payload": {
                "storyboard_id": result.get("storyboard_id"),
                "status": result.get("status"),
                "shots_count": len(result.get("shots") or []),
                "output_count": delivery.get("output_count"),
                "quality_passed": validation.get("all_passed"),
            },
        },
        {"kind": "delivery.generated", "payload": deepcopy(delivery)},
    ]


def get_creative_runtime_view(run_id: str, tenant_id: str) -> dict | None:
    production = _production_runtime_runs.get(run_id)
    if production is not None and production.get("tenant_id") == tenant_id:
        return deepcopy(production)

    media_task = _media_runtime_tasks.get(run_id)
    if media_task is not None and media_task.get("tenant_id") == tenant_id:
        return deepcopy(media_task)
    return None


@router.get("/media/models", summary="列出可用媒体生成模型(图像/视频)")
async def media_models(
    kind: str | None = None,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    mk = MediaKind(kind) if kind else None
    cards = get_media_registry().list_models(mk)
    return {
        "models": [
            {
                "model_id": c.model_id,
                "name": c.name,
                "kind": c.kind.value,
                "provider": c.provider,
                "modes": [m.value for m in c.modes],
                "description": c.description,
                "max_duration_seconds": c.max_duration_seconds,
                "resolutions": c.resolutions,
            }
            for c in cards
        ]
    }


@router.post("/media/generate", summary="媒体生成(文生图/图生图/文生视频/图生视频)")
async def media_generate(
    body: MediaGenIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    req = GenerationRequest(
        kind=MediaKind(body.kind),
        prompt=body.prompt,
        mode=GenerationMode(body.mode),
        model_id=body.model_id,
        reference_images=body.reference_images,
        duration_seconds=body.duration_seconds,
        resolution=body.resolution,
        negative_prompt=body.negative_prompt,
        seed=body.seed,
        params=dict(body.mode_settings or {}),
    )
    task = await get_media_registry().generate(req, wait=body.wait)
    if task.task_id:
        _media_task_tenants[task.task_id] = principal.tenant_id
        await creative_persistence.save_media_task_tenant(task.task_id, principal.tenant_id)
        creative_kind = f"creative.media.{body.kind}"
        input_payload = {
            "prompt": body.prompt,
            "mode": body.mode,
            "kind": body.kind,
            "wait": body.wait,
        }
        runtime_task, artifacts, delivery, preview_summary, evidence = _build_media_task_state(
            task_id=task.task_id,
            tenant_id=principal.tenant_id,
            owner_id=principal.user_id,
            kind=creative_kind,
            provider=task.provider,
            status=task.status,
            input_payload=input_payload,
            outputs=list(task.outputs),
            error=task.error or "",
        )
        _media_runtime_tasks[task.task_id] = {
            "run_id": task.task_id,
            "tenant_id": principal.tenant_id,
            "task": runtime_task,
            "workflow": None,
            "evidence": evidence,
            "artifacts": artifacts,
            "validation": {"risks": []},
            "delivery": delivery,
            "related_tasks": [],
        }
        await _persist_creative_runtime_state(
            session,
            task_view=runtime_task,
            validation={"risks": []},
            delivery=delivery,
            preview_summary=preview_summary,
            artifacts=artifacts,
            evidence=evidence,
        )
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.media_generate",
        resource="creative",
        detail={"kind": body.kind, "mode": body.mode, "provider": task.provider},
    )
    return {
        "task_id": task.task_id,
        "provider": task.provider,
        "status": task.status,
        "outputs": task.outputs,
        "error": task.error,
    }


@router.get("/media/tasks/{task_id}", summary="查询媒体生成任务状态")
async def media_task(
    task_id: str,
    principal: Principal = Depends(require_permission("creative", "read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _hydrate_from_persistence()
    owner = _media_task_tenants.get(task_id)
    if owner is None or owner != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "媒体任务不存在或无权访问")
    task = await get_media_registry().poll_task(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "媒体任务不存在")
    runtime_view = _media_runtime_tasks.get(task_id)
    kind = f"creative.media.{(get_media_registry().kind_of(task_id) or MediaKind.image).value}"
    owner_id = principal.user_id
    input_payload: dict[str, Any] = {}
    validation: dict[str, Any] = {}

    if runtime_view is not None:
        owner_id = str(runtime_view.get("task", {}).get("owner_id") or principal.user_id)
        input_payload = deepcopy(runtime_view.get("task", {}).get("input") or {})
        validation = deepcopy(runtime_view.get("validation") or {})
    else:
        persisted = await _load_persisted_media_runtime_view(
            session,
            task_id=task_id,
            tenant_id=principal.tenant_id,
        )
        if persisted is not None:
            owner_id = str(persisted.get("task", {}).get("owner_id") or principal.user_id)
            input_payload = deepcopy(persisted.get("task", {}).get("input") or {})
            validation = deepcopy(persisted.get("validation") or {})
            runtime_view = persisted
        else:
            runtime_view = _restore_media_runtime_view(
                task_id=task_id,
                tenant_id=principal.tenant_id,
                owner_id=principal.user_id,
                kind=kind,
                input_payload={},
            )
        _media_runtime_tasks[task_id] = runtime_view

    updated_task, updated_artifacts, updated_delivery, preview_summary, evidence = (
        _build_media_task_state(
            task_id=task.task_id,
            tenant_id=principal.tenant_id,
            owner_id=owner_id,
            kind=kind,
            provider=task.provider,
            status=task.status,
            input_payload=input_payload,
            outputs=list(task.outputs),
            error=task.error or "",
        )
    )
    runtime_view["task"] = updated_task
    runtime_view["artifacts"] = updated_artifacts
    runtime_view["delivery"] = updated_delivery
    runtime_view["validation"] = validation
    runtime_view["evidence"] = evidence
    await _persist_creative_runtime_state(
        session,
        task_view=updated_task,
        validation=validation,
        delivery=updated_delivery,
        preview_summary=preview_summary,
        artifacts=updated_artifacts,
        evidence=evidence,
    )
    return {
        "task_id": task.task_id,
        "kind": (get_media_registry().kind_of(task_id) or MediaKind.image).value,
        "provider": task.provider,
        "status": task.status,
        "outputs": task.outputs,
        "error": task.error,
    }


class ProduceIn(BaseModel):
    brief: str = Field(..., min_length=1)
    genre: str = "逆袭"
    platform: str = "抖音"
    target_duration_seconds: float = 60.0
    with_video: bool = True


def _attach_timeline_snapshot(doc: dict[str, Any]) -> dict[str, Any]:
    timeline_id = str(doc.get("timeline_id") or "")
    timeline = get_timeline(timeline_id) if timeline_id else None
    doc["timeline"] = timeline.to_dict() if timeline is not None else None
    if timeline_id and timeline is None:
        doc["status"] = "partial"
        doc.setdefault("failures", []).append("timeline_snapshot_missing")
    return doc


@router.post("/produce", summary="短剧全链路产出(故事板→关键帧→视频→质量门)")
async def produce(
    body: ProduceIn,
    principal: Principal = Depends(require_permission("creative", "execute")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await produce_short_drama(
        body.brief,
        genre=body.genre,
        platform=body.platform,
        target_duration_seconds=body.target_duration_seconds,
        with_video=body.with_video,
    )
    doc = result.to_dict()
    doc["tenant_id"] = principal.tenant_id
    doc["owner"] = principal.user_id
    _attach_timeline_snapshot(doc)
    _productions[result.storyboard_id] = doc
    await creative_persistence.save_production(doc)
    artifacts = _build_production_artifacts(
        run_id=result.storyboard_id,
        tenant_id=principal.tenant_id,
        result=doc,
    )
    validation = _build_production_validation_summary(doc)
    delivery = _attach_delivery_bundle(
        delivery=_build_production_delivery_summary(
            result=doc,
            artifacts=artifacts,
            validation=validation,
        ),
        artifacts=artifacts,
        validation=validation,
    )
    input_payload = {
        "brief": body.brief,
        "genre": body.genre,
        "platform": body.platform,
        "target_duration_seconds": body.target_duration_seconds,
        "with_video": body.with_video,
    }
    runtime_task = _build_creative_task_view(
        task_id=result.storyboard_id,
        tenant_id=principal.tenant_id,
        owner_id=principal.user_id,
        kind="creative.produce",
        backend="creative_studio",
        status=str(doc["status"]),
        input_payload=input_payload,
        result={
            "storyboard_id": result.storyboard_id,
            "status": doc["status"],
            "title": doc.get("title", ""),
            "timeline_id": doc.get("timeline_id"),
            "shots": deepcopy(doc.get("shots") or []),
            "shots_count": len(result.shots),
        },
    )
    preview_summary = {
        "storyboard_id": result.storyboard_id,
        "title": doc.get("title", ""),
        "shots_count": len(result.shots),
        "timeline_id": doc.get("timeline_id"),
    }
    evidence = _build_production_evidence(
        input_payload=input_payload,
        result=runtime_task["result"],
        validation=validation,
        delivery=delivery,
    )
    _production_runtime_runs[result.storyboard_id] = {
        "run_id": result.storyboard_id,
        "tenant_id": principal.tenant_id,
        "task": runtime_task,
        "workflow": None,
        "evidence": evidence,
        "artifacts": artifacts,
        "validation": validation,
        "delivery": delivery,
        "related_tasks": [],
    }
    await _persist_creative_runtime_state(
        session,
        task_view=runtime_task,
        validation=validation,
        delivery=delivery,
        preview_summary=preview_summary,
        artifacts=artifacts,
        evidence=evidence,
    )
    get_audit_log().record(
        tenant_id=principal.tenant_id,
        actor=principal.user_id,
        action="creative.produce",
        resource="creative",
        detail={
            "storyboard_id": result.storyboard_id,
            "shots": len(result.shots),
            "status": doc["status"],
        },
    )
    return doc


@router.get("/productions", summary="列出当前租户成片产物")
async def list_productions(
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    await _hydrate_from_persistence()
    items = [p for p in _productions.values() if p.get("tenant_id") == principal.tenant_id]
    return {"productions": items}


@router.get("/productions/{storyboard_id}", summary="查看成片产物详情")
async def get_production(
    storyboard_id: str,
    principal: Principal = Depends(require_permission("creative", "read")),
) -> dict:
    await _hydrate_from_persistence()
    doc = _productions.get(storyboard_id)
    if doc is None or doc.get("tenant_id") != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "产物不存在或无权访问")
    return doc
