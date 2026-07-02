"""Agent task ORM：统一 runtime task 读模型的持久化承载。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AgentTaskORM(Base):
    __tablename__ = "agent_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(64), default="agent.run", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    backend: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    intent_type: Mapped[str] = mapped_column(String(32), default="general", nullable=False)
    route_source: Mapped[str] = mapped_column(String(32), default="fallback", nullable=False)
    input_payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    validation_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    delivery_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    lineage_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    preview_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
