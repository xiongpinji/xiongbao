"""Checkpoint 领域记录。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CheckpointRecord:
    checkpoint_id: str
    tenant_id: str
    conversation_id: str
    run_id: str
    parent_checkpoint_id: str
    step: int
    status: str
    goal: str
    messages: list[dict[str, Any]]
    changed_files: list[str]
    resumed_run_id: str
    rollback_source: str
    rollback_commit: str
    rollback_error: str
    created_at: datetime
    updated_at: datetime
