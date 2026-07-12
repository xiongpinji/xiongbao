"""后台任务 Worker：长任务 / 工作流异步执行。

lite：进程内 asyncio 后台任务（立即返回 task_id，后台跑）。
full/enterprise：Celery worker（见 apps/worker）。

此处提供进程内 TaskRunner，路由可 submit 后立即返回，客户端轮询状态。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from functools import lru_cache
from typing import Any

from xagent.core.orchestration.task_view import build_task_view
from xagent.infra.logging import get_logger

logger = get_logger("xagent.worker")


class TaskStatus(str, Enum):  # noqa: UP042
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


@dataclass
class TaskRecord:
    task_id: str
    kind: str
    tenant_id: str
    owner_id: str = ""
    input_payload: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.pending
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result_payload = (
            self.result
            if isinstance(self.result, dict)
            else ({"value": self.result} if self.result is not None else {})
        )
        return build_task_view(
            task_id=self.task_id,
            run_id=None,
            tenant_id=self.tenant_id,
            owner_id=self.owner_id,
            kind=self.kind,
            backend="inproc",
            status=self.status.value,
            input_payload=deepcopy(self.input_payload),
            result=deepcopy(result_payload),
            error=self.error,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            source="task",
            route_source="fallback",
        )


class TaskRunner:
    """进程内后台任务运行器（lite）。"""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def submit(
        self,
        coro_factory: Callable[[], Awaitable[Any]],
        *,
        kind: str,
        tenant_id: str,
        owner_id: str = "",
        input_payload: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> str:
        task_id = task_id or uuid.uuid4().hex
        rec = TaskRecord(
            task_id=task_id,
            kind=kind,
            tenant_id=tenant_id,
            owner_id=owner_id,
            input_payload=deepcopy(input_payload or {}),
        )
        self._tasks[task_id] = rec
        asyncio.create_task(self._run(task_id, coro_factory, rec))
        return task_id

    async def _run(self, task_id, coro_factory, rec: TaskRecord) -> None:
        rec.status = TaskStatus.running
        rec.started_at = datetime.now(UTC).isoformat()
        try:
            rec.result = await coro_factory()
            rec.status = TaskStatus.succeeded
        except Exception as exc:
            rec.status = TaskStatus.failed
            rec.error = str(exc)
            logger.warning("worker_task_failed", task_id=task_id, error=str(exc))
        finally:
            rec.finished_at = datetime.now(UTC).isoformat()

    def get(self, task_id: str, tenant_id: str) -> TaskRecord | None:
        rec = self._tasks.get(task_id)
        if rec is None or rec.tenant_id != tenant_id:
            return None
        return rec

    def list(self, tenant_id: str) -> list[TaskRecord]:
        return [r for r in self._tasks.values() if r.tenant_id == tenant_id]


@lru_cache
def get_task_runner() -> TaskRunner:
    return TaskRunner()


def reset_task_runner() -> None:
    get_task_runner.cache_clear()
