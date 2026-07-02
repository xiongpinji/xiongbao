"""Artifact ORM：统一 runtime 产物与摘要持久化。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ArtifactORM(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    name: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    uri: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    validation_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    delivery_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    lineage_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    preview_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
