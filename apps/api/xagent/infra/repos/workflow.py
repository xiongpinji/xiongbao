"""工作流 repository：持久化运行记录（结构化视图 JSON）。"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xagent.infra.logging import get_logger
from xagent.infra.models.workflow import WorkflowRunORM

logger = get_logger("xagent.repos.workflow")


async def persist_workflow_run(session: AsyncSession, view: dict) -> None:
    """upsert 工作流运行视图；由调用方决定事务边界。"""
    run_id = view["run_id"]
    existing = await session.get(WorkflowRunORM, run_id)
    if existing:
        existing.status = view.get("status", existing.status)
        existing.spec_name = view.get("spec_name", existing.spec_name)
        existing.view = json.dumps(view, ensure_ascii=False)
        return

    session.add(
        WorkflowRunORM(
            run_id=run_id,
            tenant_id=view["tenant_id"],
            spec_name=view.get("spec_name", ""),
            status=view.get("status", "pending"),
            view=json.dumps(view, ensure_ascii=False),
        )
    )


async def load_workflow_run(
    session: AsyncSession,
    tenant_id: str,
    run_id: str,
) -> dict | None:
    try:
        stmt = select(WorkflowRunORM).where(
            WorkflowRunORM.run_id == run_id,
            WorkflowRunORM.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return json.loads(row.view)
    except Exception as exc:
        logger.warning(
            "load_workflow_run_failed",
            tenant_id=tenant_id,
            run_id=run_id,
            error=str(exc),
        )
        return None


async def load_workflow_runs(session: AsyncSession, tenant_id: str, limit: int = 50) -> list[dict]:
    try:
        stmt = (
            select(WorkflowRunORM)
            .where(WorkflowRunORM.tenant_id == tenant_id)
            .order_by(WorkflowRunORM.started_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [json.loads(r.view) for r in result.scalars()]
    except Exception as exc:
        logger.warning("load_workflow_failed", tenant_id=tenant_id, error=str(exc))
        return []
