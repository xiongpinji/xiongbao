"""后台任务路由：提交 agent 运行为后台任务 + 查询状态。

这里固化的是 task contract foundation，供后续 /runs 聚合接口复用；
并不代表 workflow 等所有 runtime 读路径都已完成统一。
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from xagent.core.orchestration import run_agent
from xagent.core.orchestration.task_view import build_task_view
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission
from xagent.infra.db import get_sessionmaker
from xagent.infra.logging import get_logger
from xagent.infra.models.agent_task import AgentTaskORM
from xagent.infra.repos.spine import attach_run_to_task
from xagent.worker import get_task_runner
from xagent.worker.celery_app import (
    get_celery_app,
    load_persisted_agent_task,
    persist_submitted_agent_task,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = get_logger("xagent.tasks")

# 过渡期索引：仅用于 inproc / Celery 读路径之间的短时桥接。
# 局限：它依赖 API 进程内存，进程重启后会丢失，因此不能作为 full / Celery
# 的唯一事实来源；持久化续查必须回退到 agent_tasks 表。
_task_tenants: dict[str, str] = {}
_task_metadata: dict[str, dict[str, Any]] = {}


class TaskSubmitIn(BaseModel):
    goal: str = Field(..., min_length=1)
    role: str | None = None
    capabilities: list[str] = Field(default_factory=list)


def _build_input_payload(body: TaskSubmitIn) -> dict[str, Any]:
    return {
        "goal": body.goal,
        "role": body.role,
        "capabilities": list(body.capabilities),
    }


def _remember_task(
    *,
    task_id: str,
    principal: Principal,
    backend: str,
    kind: str,
    input_payload: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    metadata = {
        "task_id": task_id,
        "run_id": task_id,
        "tenant_id": principal.tenant_id,
        "owner_id": principal.user_id,
        "backend": backend,
        "kind": kind,
        "input_payload": deepcopy(input_payload),
        "created_at": created_at or datetime.now(UTC).isoformat(),
    }
    _task_tenants[task_id] = principal.tenant_id
    _task_metadata[task_id] = metadata
    return metadata


def _build_metadata_view(
    metadata: dict[str, Any],
    *,
    status_value: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    return build_task_view(
        task_id=str(metadata["task_id"]),
        run_id=None,
        tenant_id=str(metadata["tenant_id"]),
        owner_id=str(metadata.get("owner_id") or ""),
        kind=str(metadata.get("kind") or "agent.run"),
        backend=str(metadata.get("backend") or "inproc"),
        status=status_value,
        input_payload=deepcopy(metadata.get("input_payload") or {}),
        result=deepcopy(result or {}),
        error=error or "",
        created_at=str(metadata.get("created_at") or "") or None,
        started_at=started_at,
        finished_at=finished_at,
        updated_at=updated_at,
        source="task",
        route_source="fallback",
    )


def _principal_from_metadata(metadata: dict[str, Any]) -> Principal:
    return Principal(
        user_id=str(metadata.get("owner_id") or ""),
        tenant_id=str(metadata.get("tenant_id") or ""),
        roles=frozenset({"member"}),
    )


async def _load_persisted_task_views(tenant_id: str) -> dict[str, dict[str, Any]]:
    try:
        async with get_sessionmaker()() as session:
            rows = (
                (
                    await session.execute(
                        select(AgentTaskORM)
                        .where(AgentTaskORM.tenant_id == tenant_id)
                        .order_by(AgentTaskORM.created_at.asc(), AgentTaskORM.task_id.asc())
                    )
                )
                .scalars()
                .all()
            )
    except Exception as exc:
        logger.warning(
            "load_persisted_task_views_failed",
            tenant_id=tenant_id,
            error=str(exc),
        )
        return {}

    task_views: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            task_views[row.task_id] = build_task_view(
                task_id=row.task_id,
                run_id=row.run_id,
                tenant_id=row.tenant_id,
                owner_id=row.owner_id,
                kind=row.kind,
                backend=row.backend,
                status=row.status,
                input_payload=json.loads(row.input_payload or "{}"),
                result=json.loads(row.result_payload or "{}"),
                error=row.error,
                created_at=row.created_at.isoformat() if row.created_at else None,
                started_at=row.started_at.isoformat() if row.started_at else None,
                finished_at=row.finished_at.isoformat() if row.finished_at else None,
                updated_at=row.updated_at.isoformat() if row.updated_at else None,
                source=row.source,
                intent_type=row.intent_type,
                route_source=row.route_source,
            )
        except Exception as exc:
            logger.warning(
                "build_persisted_task_view_failed",
                task_id=row.task_id,
                tenant_id=tenant_id,
                error=str(exc),
            )
            continue
    return task_views


async def _try_attach_spine_task(
    *,
    task_id: str,
    task_title: str,
    principal: Principal,
) -> dict[str, str] | None:
    try:
        async with get_sessionmaker()() as session:
            linkage = await attach_run_to_task(
                session,
                tenant_id=principal.tenant_id,
                task_title=task_title,
                run_id=task_id,
            )
            if linkage is None:
                return None
            await session.commit()
            return linkage
    except Exception as exc:
        logger.warning(
            "attach_spine_task_failed",
            task_id=task_id,
            tenant_id=principal.tenant_id,
            error=str(exc),
        )
        return None


@router.post("", summary="提交 agent 运行为后台任务")
async def submit_task(
    body: TaskSubmitIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
) -> dict:
    runner = get_task_runner()
    input_payload = _build_input_payload(body)

    async def _run():
        return (
            await run_agent(
                body.goal,
                principal=principal,
                role_name=body.role,
                capabilities=set(body.capabilities) or None,
            )
        ).to_dict()

    # full 模式 + Celery 可用 -> 走 Celery；否则进程内
    try:
        celery_app = get_celery_app()
        if celery_app is not None:
            async_result = celery_app.send_task(
                "xagent.run_agent",
                kwargs={
                    "goal": body.goal,
                    "role": body.role,
                    "capabilities": body.capabilities,
                    "tenant_id": principal.tenant_id,
                    "user_id": principal.user_id,
                },
            )
            metadata = _remember_task(
                task_id=async_result.id,
                principal=principal,
                backend="celery",
                kind="agent.run",
                input_payload=input_payload,
            )
            try:
                await persist_submitted_agent_task(
                    task_id=str(async_result.id),
                    tenant_id=principal.tenant_id,
                    owner_id=principal.user_id,
                    kind="agent.run",
                    backend="celery",
                    input_payload=input_payload,
                    status="pending",
                )
            except Exception as exc:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    f"后台任务已投递但初始持久化失败：{exc}",
                ) from exc
            await _try_attach_spine_task(
                task_id=str(async_result.id),
                task_title=body.goal,
                principal=principal,
            )
            return _build_metadata_view(metadata, status_value="pending")
    except HTTPException:
        raise
    except Exception:  # noqa: S110  Celery 发送失败降级进程内
        pass

    task_id = runner.submit(
        _run,
        kind="agent.run",
        tenant_id=principal.tenant_id,
        owner_id=principal.user_id,
        input_payload=input_payload,
    )
    metadata = _remember_task(
        task_id=task_id,
        principal=principal,
        backend="inproc",
        kind="agent.run",
        input_payload=input_payload,
    )
    await _try_attach_spine_task(
        task_id=task_id,
        task_title=body.goal,
        principal=principal,
    )
    return _build_metadata_view(metadata, status_value="pending")


async def get_task_runtime_view(task_id: str, tenant_id: str) -> dict[str, Any] | None:
    # 先查进程内 TaskRunner
    rec = get_task_runner().get(task_id, tenant_id)
    if rec is not None:
        return rec.to_dict()

    # full / Celery 的主事实来源是持久化 agent_tasks；内存索引只做短时缓存桥接。
    persisted = await load_persisted_agent_task(task_id, tenant_id)
    if persisted is not None:
        metadata = _remember_task(
            task_id=task_id,
            principal=_principal_from_metadata(persisted),
            backend=str(persisted.get("backend") or "celery"),
            kind=str(persisted.get("kind") or "agent.run"),
            input_payload=deepcopy(persisted.get("input") or {}),
            created_at=str(persisted.get("created_at") or "") or None,
        )
        _task_tenants[task_id] = str(persisted.get("tenant_id") or tenant_id)
        _task_metadata[task_id] = metadata
        persisted_status = str(persisted.get("status") or "").lower()
        persisted_backend = str(persisted.get("backend") or "").lower()
        if persisted_backend != "celery" or persisted_status in {"succeeded", "failed"}:
            return persisted
        metadata = _task_metadata.get(task_id) or metadata

    # 进程内没有 -> 查 Celery backend（先校验租户归属）
    owner = _task_tenants.get(task_id)
    metadata = _task_metadata.get(task_id)
    if owner is None and metadata is None:
        return None
    if owner is not None and owner != tenant_id:
        return None

    try:
        celery_app = get_celery_app()
        if celery_app is not None:
            async_result = celery_app.AsyncResult(task_id)
            status_map = {
                "PENDING": "pending",
                "STARTED": "running",
                "SUCCESS": "succeeded",
                "FAILURE": "failed",
                "RETRY": "running",
            }
            task_status = status_map.get(async_result.state, async_result.state.lower())
            result = async_result.result if async_result.successful() else {}
            error = str(async_result.result) if async_result.failed() else ""
            metadata = metadata or {
                "task_id": task_id,
                "run_id": task_id,
                "tenant_id": tenant_id,
                "owner_id": "",
                "backend": "celery",
                "kind": "agent.run",
                "input_payload": {},
                "created_at": None,
            }
            return _build_metadata_view(
                metadata,
                status_value=task_status,
                result=result if isinstance(result, dict) else {"value": result},
                error=error,
            )
    except Exception:  # noqa: S110  Celery 查询失败降级内存合同
        pass

    if metadata is not None and metadata.get("tenant_id") == tenant_id:
        return _build_metadata_view(metadata, status_value="pending")
    return None


@router.get("/{task_id}", summary="查询任务状态")
async def get_task(
    task_id: str,
    principal: Principal = Depends(require_permission("agent", "read")),
) -> dict:
    task_view = await get_task_runtime_view(task_id, principal.tenant_id)
    if task_view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在或无权访问")
    return task_view


@router.get("", summary="列出当前租户任务")
async def list_tasks(
    principal: Principal = Depends(require_permission("agent", "read")),
) -> dict:
    recs = get_task_runner().list(principal.tenant_id)
    tasks_by_id = {r.task_id: r.to_dict() for r in recs}

    persisted_tasks = await _load_persisted_task_views(principal.tenant_id)
    for task_id in persisted_tasks:
        refreshed_view = await get_task_runtime_view(task_id, principal.tenant_id)
        tasks_by_id[task_id] = refreshed_view or persisted_tasks[task_id]

    for task_id, metadata in _task_metadata.items():
        if metadata.get("tenant_id") != principal.tenant_id or task_id in tasks_by_id:
            continue
        fallback_view = await get_task_runtime_view(task_id, principal.tenant_id)
        tasks_by_id[task_id] = fallback_view or _build_metadata_view(
            metadata, status_value="pending"
        )

    tasks = sorted(
        tasks_by_id.values(),
        key=lambda item: (
            str(item.get("created_at") or item.get("updated_at") or ""),
            str(item.get("task_id") or ""),
        ),
        reverse=True,
    )
    return {"tasks": tasks}
