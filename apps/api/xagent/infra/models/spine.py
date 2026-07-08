from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class GoalORM(Base):
    __tablename__ = "delivery_goals"

    goal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    phase: Mapped[str] = mapped_column(String(32), default="planning", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


class InitiativeORM(Base):
    __tablename__ = "delivery_initiatives"

    initiative_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("delivery_goals.goal_id"), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


class DeliveryTaskORM(Base):
    __tablename__ = "delivery_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("delivery_initiatives.initiative_id"), index=True, nullable=False
    )
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("delivery_goals.goal_id"), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    task_kind: Mapped[str] = mapped_column(
        String(32), default="execution", nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    blocker_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


class ReleaseRecordORM(Base):
    __tablename__ = "release_records"

    release_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("delivery_goals.goal_id"), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    branch_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    pr_number: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
