"""后台任务 Worker：长任务 / 工作流异步执行。

lite：进程内 asyncio 后台任务（立即返回 task_id，后台跑）。
full/enterprise：Celery worker（见 apps/worker）。

此处提供进程内 TaskRunner，路由可 submit 后立即返回，客户端轮询状态。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from functools import lru_cache
from typing import Any

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
    status: TaskStatus = TaskStatus.pending
    result: Any = None
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    finished_at: str | None = None


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
    ) -> str:
        task_id = uuid.uuid4().hex
        rec = TaskRecord(task_id=task_id, kind=kind, tenant_id=tenant_id)
        self._tasks[task_id] = rec
        asyncio.create_task(self._run(task_id, coro_factory, rec))
        return task_id

    async def _run(self, task_id, coro_factory, rec: TaskRecord) -> None:
        rec.status = TaskStatus.running
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
