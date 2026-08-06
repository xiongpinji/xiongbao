"""租户会话 checkpoint 持久模型。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CheckpointORM(Base):
    __tablename__ = "checkpoints"

    checkpoint_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(96), index=True, nullable=False)
    parent_checkpoint_id: Mapped[str] = mapped_column(
        String(64), index=True, default="", nullable=False
    )
    step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    messages_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    changed_files_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    resumed_run_id: Mapped[str] = mapped_column(String(96), default="", nullable=False)
    rollback_source: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    rollback_commit: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    rollback_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
