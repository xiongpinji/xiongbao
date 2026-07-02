"""Celery worker 集成（full/enterprise 模式）。

进程内 TaskRunner 为 lite 默认；配置 Redis broker 后，submit 可走 Celery
实现多实例横向扩展。两者接口一致（submit -> task_id -> poll）。

用法：
  celery -A xagent.worker.celery_app worker --loglevel=info
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from xagent.infra.logging import get_logger
from xagent.infra.settings import get_settings

logger = get_logger("xagent.celery")

_celery_app = None
_TERMINAL_STATUSES = {"succeeded", "failed"}


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


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _upsert_agent_task(
    session: AsyncSession,
    *,
    task_id: str,
    run_id: str | None = None,
    tenant_id: str,
    owner_id: str,
    kind: str,
    backend: str,
    status: str,
    input_payload: dict[str, Any] | None = None,
    result_payload: dict[str, Any] | None = None,
    error: str = "",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    validation_summary: dict[str, Any] | None = None,
    delivery_summary: dict[str, Any] | None = None,
    lineage_summary: dict[str, Any] | None = None,
    preview_summary: dict[str, Any] | None = None,
) -> None:
    from xagent.infra.models.agent_task import AgentTaskORM

    row = await session.get(AgentTaskORM, task_id)
    resolved_run_id = (run_id or task_id).strip() or task_id
    if row is None:
        row = AgentTaskORM(
            task_id=task_id,
            run_id=resolved_run_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            kind=kind,
            status=status,
            backend=backend,
            source="task",
            intent_type="agent",
            route_source="fallback",
            input_payload=json.dumps(input_payload or {}, ensure_ascii=False),
            result_payload=json.dumps(result_payload or {}, ensure_ascii=False),
            error=error,
            validation_summary=json.dumps(validation_summary or {}, ensure_ascii=False),
            delivery_summary=json.dumps(delivery_summary or {}, ensure_ascii=False),
            lineage_summary=json.dumps(lineage_summary or {}, ensure_ascii=False),
            preview_summary=json.dumps(preview_summary or {}, ensure_ascii=False),
            started_at=started_at,
            finished_at=finished_at,
        )
        session.add(row)
    else:
        current_status = str(row.status or "").strip().lower()
        next_status = str(status or "").strip().lower()
        row.run_id = resolved_run_id
        row.tenant_id = tenant_id
        row.owner_id = owner_id
        row.kind = kind
        row.backend = backend
        row.source = "task"
        row.intent_type = "agent"
        row.route_source = "fallback"
        row.input_payload = json.dumps(input_payload or {}, ensure_ascii=False)
        row.validation_summary = json.dumps(validation_summary or {}, ensure_ascii=False)
        row.delivery_summary = json.dumps(delivery_summary or {}, ensure_ascii=False)
        row.lineage_summary = json.dumps(lineage_summary or {}, ensure_ascii=False)
        row.preview_summary = json.dumps(preview_summary or {}, ensure_ascii=False)

        terminal_locked = (
            current_status in _TERMINAL_STATUSES and next_status not in _TERMINAL_STATUSES
        )
        if not terminal_locked:
            row.status = status
            row.result_payload = json.dumps(result_payload or {}, ensure_ascii=False)
            row.error = error
            row.started_at = started_at
            row.finished_at = finished_at
        else:
            if not row.result_payload:
                row.result_payload = json.dumps(result_payload or {}, ensure_ascii=False)
            if not row.error and error:
                row.error = error
            if row.started_at is None and started_at is not None:
                row.started_at = started_at
            if row.finished_at is None and finished_at is not None:
                row.finished_at = finished_at


async def persist_submitted_agent_task(
    *,
    task_id: str,
    tenant_id: str,
    owner_id: str,
    kind: str,
    backend: str,
    input_payload: dict[str, Any],
    status: str = "pending",
) -> None:
    await persist_agent_task_record(
        task_id=task_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        kind=kind,
        backend=backend,
        status=status,
        input_payload=input_payload,
    )


async def persist_agent_task_record_in_session(
    session: AsyncSession,
    *,
    task_id: str,
    run_id: str | None = None,
    tenant_id: str,
    owner_id: str,
    kind: str,
    backend: str,
    status: str,
    input_payload: dict[str, Any],
    result_payload: dict[str, Any] | None = None,
    error: str = "",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    validation_summary: dict[str, Any] | None = None,
    delivery_summary: dict[str, Any] | None = None,
    lineage_summary: dict[str, Any] | None = None,
    preview_summary: dict[str, Any] | None = None,
) -> None:
    await _upsert_agent_task(
        session,
        task_id=task_id,
        run_id=run_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        kind=kind,
        backend=backend,
        status=status,
        input_payload=input_payload,
        result_payload=result_payload,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
        validation_summary=validation_summary,
        delivery_summary=delivery_summary,
        lineage_summary=lineage_summary,
        preview_summary=preview_summary,
    )


async def persist_agent_task_record(
    *,
    task_id: str,
    run_id: str | None = None,
    tenant_id: str,
    owner_id: str,
    kind: str,
    backend: str,
    status: str,
    input_payload: dict[str, Any],
    result_payload: dict[str, Any] | None = None,
    error: str = "",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    validation_summary: dict[str, Any] | None = None,
    delivery_summary: dict[str, Any] | None = None,
    lineage_summary: dict[str, Any] | None = None,
    preview_summary: dict[str, Any] | None = None,
) -> None:
    from xagent.infra.db import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            await persist_agent_task_record_in_session(
                session,
                task_id=task_id,
                run_id=run_id,
                tenant_id=tenant_id,
                owner_id=owner_id,
                kind=kind,
                backend=backend,
                status=status,
                input_payload=input_payload,
                result_payload=result_payload,
                error=error,
                started_at=started_at,
                finished_at=finished_at,
                validation_summary=validation_summary,
                delivery_summary=delivery_summary,
                lineage_summary=lineage_summary,
                preview_summary=preview_summary,
            )
            await session.commit()
    except Exception as exc:
        if _is_schema_mismatch(exc, "agent_tasks"):
            logger.warning(
                "persist_agent_task_skipped",
                task_id=task_id,
                tenant_id=tenant_id,
                error=str(exc),
            )
            return
        raise


async def load_persisted_agent_task(
    task_id: str,
    tenant_id: str,
) -> dict[str, Any] | None:
    from xagent.core.orchestration.task_view import build_task_view
    from xagent.infra.db import get_sessionmaker
    from xagent.infra.models.agent_task import AgentTaskORM

    try:
        async with get_sessionmaker()() as session:
            row = await session.get(AgentTaskORM, task_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return build_task_view(
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
            "load_persisted_agent_task_failed",
            task_id=task_id,
            tenant_id=tenant_id,
            error=str(exc),
        )
        return None


def get_celery_app():
    """惰性创建 Celery app（未配置 broker 返回 None）。"""
    global _celery_app
    if _celery_app is not None:
        return _celery_app
    settings = get_settings()
    broker = settings.cache.redis_url
    if not broker:
        return None
    try:
        from celery import Celery

        _celery_app = Celery("xagent", broker=broker, backend=broker)
        _celery_app.conf.update(
            task_serializer="json",
            result_serializer="json",
            accept_content=["json"],
            task_track_started=True,
            task_time_limit=600,
            task_soft_time_limit=540,
        )
        _celery_app.task(name="xagent.run_agent")(run_agent_task)
        logger.info("celery_initialized", broker=broker)
    except ImportError:
        logger.info("celery_not_installed", detail="未安装 celery，后台任务走进程内")
        return None
    return _celery_app


def run_agent_task(
    goal: str,
    role: str | None,
    capabilities: list[str],
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Celery 任务入口：同步包装异步 run_agent。"""
    from xagent.core.orchestration import run_agent
    from xagent.enterprise.auth.principal import Principal

    principal = Principal(user_id=user_id, tenant_id=tenant_id, roles=frozenset({"member"}))
    task_id = ""
    try:
        from celery import current_task

        task_id = str(getattr(getattr(current_task, "request", None), "id", "") or "")
    except Exception:
        task_id = ""

    started_at = datetime.now(UTC)
    input_payload = {
        "goal": goal,
        "role": role,
        "capabilities": list(capabilities),
    }
    if task_id:
        asyncio.run(
            persist_submitted_agent_task(
                task_id=task_id,
                tenant_id=tenant_id,
                owner_id=user_id,
                kind="agent.run",
                backend="celery",
                input_payload=input_payload,
                status="running",
            )
        )

    try:
        result = asyncio.run(
            run_agent(
                goal,
                principal=principal,
                role_name=role,
                capabilities=set(capabilities) or None,
                run_id=task_id or None,
            )
        ).to_dict()
    except Exception as run_exc:
        run_error = str(run_exc)
        if task_id:
            from xagent.infra.db import get_sessionmaker

            async def _mark_failed() -> None:
                try:
                    async with get_sessionmaker()() as session:
                        await persist_agent_task_record_in_session(
                            session,
                            task_id=task_id,
                            run_id=task_id,
                            tenant_id=tenant_id,
                            owner_id=user_id,
                            kind="agent.run",
                            backend="celery",
                            status="failed",
                            input_payload=input_payload,
                            result_payload={},
                            error=run_error,
                            started_at=started_at,
                            finished_at=datetime.now(UTC),
                        )
                        await session.commit()
                except Exception as persist_exc:
                    if _is_schema_mismatch(persist_exc, "agent_tasks"):
                        return
                    raise

            asyncio.run(_mark_failed())
        raise

    if task_id:
        from xagent.infra.db import get_sessionmaker

        async def _mark_succeeded() -> None:
            try:
                async with get_sessionmaker()() as session:
                    await persist_agent_task_record_in_session(
                        session,
                        task_id=task_id,
                        run_id=task_id,
                        tenant_id=tenant_id,
                        owner_id=user_id,
                        kind="agent.run",
                        backend="celery",
                        status="succeeded",
                        input_payload=input_payload,
                        result_payload=result if isinstance(result, dict) else {"value": result},
                        error="",
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                    )
                    await session.commit()
            except Exception as persist_exc:
                if _is_schema_mismatch(persist_exc, "agent_tasks"):
                    return
                raise

        asyncio.run(_mark_succeeded())
    return result


# 模块级 app（celery CLI -A 需要）
app = get_celery_app()
