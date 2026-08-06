"""可审查开发任务的持久化模型。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DevelopmentTaskORM(Base):
    __tablename__ = "development_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sub_run_id: Mapped[str] = mapped_column(String(96), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    main_workspace: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    base_commit: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    target_branch: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    work_branch: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    worktree_path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    result_commit: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    applied_commit: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    diff_stat: Mapped[str] = mapped_column(Text, default="", nullable=False)
    patch_path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    test_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    conflict_files: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
