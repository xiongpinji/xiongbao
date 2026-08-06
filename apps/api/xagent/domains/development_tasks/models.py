"""开发任务领域数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DevelopmentTaskStatus(StrEnum):
    running = "running"
    awaiting_review = "awaiting_review"
    approved = "approved"
    applied = "applied"
    rejected = "rejected"
    conflict = "conflict"
    expired = "expired"
    failed = "failed"
    timeout = "timeout"
    cancelled = "cancelled"


@dataclass(frozen=True)
class DevelopmentTaskCreate:
    task_id: str
    parent_run_id: str
    sub_run_id: str
    tenant_id: str
    owner_id: str
    goal: str
    main_workspace: str
    base_commit: str
    target_branch: str
    work_branch: str
    worktree_path: str
    patch_path: str
    status: DevelopmentTaskStatus = DevelopmentTaskStatus.running
    expires_at: datetime | None = None


@dataclass(frozen=True)
class DevelopmentTaskRecord:
    task_id: str
    parent_run_id: str
    sub_run_id: str
    tenant_id: str
    owner_id: str
    goal: str
    status: DevelopmentTaskStatus
    main_workspace: str
    base_commit: str
    target_branch: str
    work_branch: str
    worktree_path: str
    result_commit: str
    applied_commit: str
    diff_stat: str
    patch_path: str
    test_summary: str
    conflict_files: str
    error: str
    reviewed_by: str
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
    applied_at: datetime | None
    expires_at: datetime | None
