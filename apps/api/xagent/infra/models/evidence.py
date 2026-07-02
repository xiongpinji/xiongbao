"""Evidence ORM：运行期校验/交付凭据的持久化。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EvidenceORM(Base):
    __tablename__ = "evidence_records"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "evidence_id", name="pk_evidence_records"),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
