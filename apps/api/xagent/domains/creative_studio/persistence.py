"""短剧工厂持久化层：草稿 / 成片产物 / 画布 / 媒体任务租户映射落库。

此前这些状态均为进程内 dict（见 api/v1/creative_studio.py、api/v1/canvas.py），
重启即丢。本模块提供异步持久化（Phase 5 落库）：

- 沿用仓库现有约定：SQLAlchemy 2.0 异步 + ``infra.db.Base`` + aiosqlite，
  复杂字段 JSON 序列化进 Text 列，租户隔离走 ``tenant_id`` 列（索引）。
- 建表策略：首次读写时惰性 ``create(checkfirst=True)``（对齐 main.py 的
  create_all 兜底），生产环境用 alembic 迁移
  ``migrations/versions/20260803_creative_studio_persistence.py``。
- 所有写操作 best-effort：DB 不可用/缺表时记 warning 并跳过，不影响 API 主流程
  （对齐 ``_persist_creative_runtime_state`` 的容错风格）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base, get_sessionmaker
from xagent.infra.logging import get_logger

logger = get_logger("xagent.creative.persistence")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CreativeDraftORM(Base):
    """工作流草稿（doc 列为 draft.to_dict() + tenant_id/owner 的 JSON）。"""

    __tablename__ = "creative_drafts"

    draft_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    owner: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False)
    doc: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class CreativeProductionORM(Base):
    """成片产物（doc 列为 ProductionResult.to_dict() + tenant_id/owner 的 JSON）。"""

    __tablename__ = "creative_productions"

    storyboard_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    owner: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    doc: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class CreativeCanvasORM(Base):
    """生产画布（doc 列为 ProductionCanvas.to_dict() 的 JSON）。"""

    __tablename__ = "creative_canvases"

    canvas_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    doc: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class CreativeMediaTaskORM(Base):
    """媒体任务 → 租户映射（按租户拉取媒体任务状态用）。"""

    __tablename__ = "creative_media_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


_CREATIVE_TABLES = (
    CreativeDraftORM.__table__,
    CreativeProductionORM.__table__,
    CreativeCanvasORM.__table__,
    CreativeMediaTaskORM.__table__,
)

_tables_ensured = False


async def ensure_creative_tables() -> bool:
    """惰性建表（每进程一次，checkfirst 幂等）。失败记 warning 并返回 False。"""
    global _tables_ensured
    if _tables_ensured:
        return True
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await session.run_sync(
                lambda s: [t.create(s.connection(), checkfirst=True) for t in _CREATIVE_TABLES]
            )
        _tables_ensured = True
        return True
    except Exception as exc:  # DB 不可用不阻断主流程
        logger.warning("creative_tables_ensure_failed", error=str(exc))
        return False


def reset_creative_table_cache() -> None:
    """重置建表标记（测试隔离/切换 DB 后用）。"""
    global _tables_ensured
    _tables_ensured = False


def _decode_doc(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def _write(op) -> None:
    """best-effort 写：建表 → 执行 → 提交；失败回滚并记 warning。"""
    if not await ensure_creative_tables():
        return
    try:
        async with get_sessionmaker()() as session:
            await op(session)
            await session.commit()
    except Exception as exc:
        logger.warning("creative_persist_failed", error=str(exc))


async def _read(op, default):
    """best-effort 读：建表 → 查询；失败返回 default。"""
    if not await ensure_creative_tables():
        return default
    try:
        async with get_sessionmaker()() as session:
            return await op(session)
    except Exception as exc:
        logger.warning("creative_load_failed", error=str(exc))
        return default


# ─── 草稿 ───


async def save_draft(doc: dict) -> None:
    """upsert 草稿（doc 含 draft_id/tenant_id/owner/status）。"""

    async def _op(session: AsyncSession) -> None:
        draft_id = str(doc.get("draft_id") or "")
        if not draft_id:
            return
        row = await session.get(CreativeDraftORM, draft_id)
        if row is None:
            row = CreativeDraftORM(draft_id=draft_id, tenant_id=str(doc.get("tenant_id") or ""))
            session.add(row)
        row.tenant_id = str(doc.get("tenant_id") or "")
        row.owner = str(doc.get("owner") or "")
        row.status = str(doc.get("status") or "pending_review")
        row.doc = json.dumps(doc, ensure_ascii=False)

    await _write(_op)


async def load_draft(draft_id: str, tenant_id: str) -> dict | None:
    async def _op(session: AsyncSession) -> dict | None:
        row = await session.get(CreativeDraftORM, draft_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _decode_doc(row.doc)

    return await _read(_op, None)


async def load_drafts(tenant_id: str) -> list[dict]:
    async def _op(session: AsyncSession) -> list[dict]:
        rows = (
            await session.execute(
                select(CreativeDraftORM)
                .where(CreativeDraftORM.tenant_id == tenant_id)
                .order_by(CreativeDraftORM.created_at.asc())
            )
        ).scalars().all()
        return [_decode_doc(r.doc) for r in rows]

    return await _read(_op, [])


async def load_all_drafts() -> dict[str, dict]:
    """全部草稿（重启恢复到进程内存储用）：draft_id → doc。"""

    async def _op(session: AsyncSession) -> dict[str, dict]:
        rows = (await session.execute(select(CreativeDraftORM))).scalars().all()
        return {r.draft_id: _decode_doc(r.doc) for r in rows}

    return await _read(_op, {})


# ─── 成片产物 ───


async def save_production(doc: dict) -> None:
    """upsert 成片产物（doc 含 storyboard_id/tenant_id/owner/status）。"""

    async def _op(session: AsyncSession) -> None:
        storyboard_id = str(doc.get("storyboard_id") or "")
        if not storyboard_id:
            return
        row = await session.get(CreativeProductionORM, storyboard_id)
        if row is None:
            row = CreativeProductionORM(
                storyboard_id=storyboard_id, tenant_id=str(doc.get("tenant_id") or "")
            )
            session.add(row)
        row.tenant_id = str(doc.get("tenant_id") or "")
        row.owner = str(doc.get("owner") or "")
        row.status = str(doc.get("status") or "pending")
        row.doc = json.dumps(doc, ensure_ascii=False)

    await _write(_op)


async def load_production(storyboard_id: str, tenant_id: str) -> dict | None:
    async def _op(session: AsyncSession) -> dict | None:
        row = await session.get(CreativeProductionORM, storyboard_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _decode_doc(row.doc)

    return await _read(_op, None)


async def load_productions(tenant_id: str) -> list[dict]:
    async def _op(session: AsyncSession) -> list[dict]:
        rows = (
            await session.execute(
                select(CreativeProductionORM)
                .where(CreativeProductionORM.tenant_id == tenant_id)
                .order_by(CreativeProductionORM.created_at.asc())
            )
        ).scalars().all()
        return [_decode_doc(r.doc) for r in rows]

    return await _read(_op, [])


async def load_all_productions() -> dict[str, dict]:
    async def _op(session: AsyncSession) -> dict[str, dict]:
        rows = (await session.execute(select(CreativeProductionORM))).scalars().all()
        return {r.storyboard_id: _decode_doc(r.doc) for r in rows}

    return await _read(_op, {})


# ─── 画布 ───


async def save_canvas(doc: dict, tenant_id: str) -> None:
    """upsert 画布（doc 为 ProductionCanvas.to_dict()）。"""

    async def _op(session: AsyncSession) -> None:
        canvas_id = str(doc.get("canvas_id") or "")
        if not canvas_id:
            return
        row = await session.get(CreativeCanvasORM, canvas_id)
        if row is None:
            row = CreativeCanvasORM(canvas_id=canvas_id, tenant_id=tenant_id)
            session.add(row)
        row.tenant_id = tenant_id
        row.doc = json.dumps(doc, ensure_ascii=False)

    await _write(_op)


async def load_canvas(canvas_id: str, tenant_id: str) -> dict | None:
    async def _op(session: AsyncSession) -> dict | None:
        row = await session.get(CreativeCanvasORM, canvas_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _decode_doc(row.doc)

    return await _read(_op, None)


async def load_all_canvases() -> dict[str, tuple[dict, str]]:
    """全部画布（重启恢复用）：canvas_id → (doc, tenant_id)。"""

    async def _op(session: AsyncSession) -> dict[str, tuple[dict, str]]:
        rows = (await session.execute(select(CreativeCanvasORM))).scalars().all()
        return {r.canvas_id: (_decode_doc(r.doc), r.tenant_id) for r in rows}

    return await _read(_op, {})


# ─── 媒体任务租户映射 ───


async def save_media_task_tenant(task_id: str, tenant_id: str) -> None:
    async def _op(session: AsyncSession) -> None:
        if not task_id:
            return
        row = await session.get(CreativeMediaTaskORM, task_id)
        if row is None:
            session.add(CreativeMediaTaskORM(task_id=task_id, tenant_id=tenant_id))
        else:
            row.tenant_id = tenant_id

    await _write(_op)


async def load_media_task_tenant(task_id: str) -> str | None:
    async def _op(session: AsyncSession) -> str | None:
        row = await session.get(CreativeMediaTaskORM, task_id)
        return row.tenant_id if row is not None else None

    return await _read(_op, None)


async def load_all_media_task_tenants() -> dict[str, str]:
    async def _op(session: AsyncSession) -> dict[str, str]:
        rows = (await session.execute(select(CreativeMediaTaskORM))).scalars().all()
        return {r.task_id: r.tenant_id for r in rows}

    return await _read(_op, {})
