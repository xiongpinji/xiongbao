"""后台任务管理：异步任务调度与追踪。

功能：
- 提交后台任务
- 任务状态追踪
- 并发控制
- 任务取消

用法：
    from xagent.api.background_tasks import task_manager

    task_id = await task_manager.submit(send_email, user_id="u1")
    status = task_manager.get_status(task_id)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.tasks")


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    """任务记录。"""

    task_id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    _asyncio_task: asyncio.Task | None = field(default=None, repr=False)


class BackgroundTaskManager:
    """后台任务管理器。"""

    def __init__(self, max_concurrent: int = 10, max_history: int = 1000):
        self._tasks: dict[str, TaskRecord] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_history = max_history
        self._total_submitted = 0

    async def submit(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        name: str = "",
        **kwargs: Any,
    ) -> str:
        """提交后台任务。返回 task_id。"""
        task_id = str(uuid.uuid4())[:8]
        record = TaskRecord(task_id=task_id, name=name or fn.__name__)
        self._tasks[task_id] = record
        self._total_submitted += 1

        asyncio_task = asyncio.create_task(self._run(task_id, fn, *args, **kwargs))
        record._asyncio_task = asyncio_task

        logger.info("task submitted: %s (%s)", task_id, record.name)
        return task_id

    async def _run(self, task_id: str, fn: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> None:
        """执行任务。"""
        record = self._tasks[task_id]

        async with self._semaphore:
            record.status = TaskStatus.RUNNING
            record.started_at = time.time()

            try:
                result = await fn(*args, **kwargs)
                record.result = result
                record.status = TaskStatus.COMPLETED
                logger.info("task completed: %s", task_id)
            except asyncio.CancelledError:
                record.status = TaskStatus.CANCELLED
                logger.info("task cancelled: %s", task_id)
            except Exception as exc:
                record.status = TaskStatus.FAILED
                record.error = str(exc)[:500]
                logger.error("task failed: %s error=%s", task_id, exc)
            finally:
                record.completed_at = time.time()

        self._cleanup_old()

    def get_status(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态。"""
        record = self._tasks.get(task_id)
        if not record:
            return None
        return {
            "task_id": record.task_id,
            "name": record.name,
            "status": record.status.value,
            "error": record.error,
            "created_at": record.created_at,
            "started_at": record.started_at,
            "completed_at": record.completed_at,
            "duration_s": (
                round((record.completed_at or time.time()) - (record.started_at or record.created_at), 2)
                if record.started_at
                else None
            ),
        }

    def cancel(self, task_id: str) -> bool:
        """取消任务。"""
        record = self._tasks.get(task_id)
        if not record or record._asyncio_task is None:
            return False
        if record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return False
        record._asyncio_task.cancel()
        return True

    def list_tasks(self, status: TaskStatus | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """列出任务。"""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return [
            {
                "task_id": t.task_id,
                "name": t.name,
                "status": t.status.value,
                "created_at": t.created_at,
            }
            for t in tasks[:limit]
        ]

    def get_stats(self) -> dict[str, Any]:
        """获取统计。"""
        statuses = {}
        for t in self._tasks.values():
            statuses[t.status.value] = statuses.get(t.status.value, 0) + 1
        return {
            "total_submitted": self._total_submitted,
            "by_status": statuses,
        }

    def _cleanup_old(self) -> None:
        """清理历史记录。"""
        if len(self._tasks) > self._max_history:
            completed = [
                tid for tid, t in self._tasks.items()
                if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            ]
            completed.sort(key=lambda tid: self._tasks[tid].created_at)
            for tid in completed[: len(completed) // 2]:
                del self._tasks[tid]


# 全局实例
task_manager = BackgroundTaskManager()
