"""任务调度器：定时/延迟任务执行。

功能：
- Cron 风格定时任务
- 一次性延迟任务
- 任务取消/暂停
- 执行历史

用法：
    from xagent.api.task_scheduler import scheduler

    @scheduler.cron("cleanup", interval_s=3600)
    async def cleanup_expired():
        await db.delete_expired()

    scheduler.schedule_once("report", delay_s=60, fn=generate_report)
    await scheduler.start()
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.scheduler")


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """调度任务。"""

    name: str
    fn: Callable[[], Coroutine[Any, Any, None]]
    interval_s: float | None = None  # None = 一次性
    delay_s: float = 0.0
    status: TaskStatus = TaskStatus.PENDING
    last_run: float = 0.0
    next_run: float = 0.0
    run_count: int = 0
    error_count: int = 0
    last_error: str = ""
    _task: asyncio.Task | None = field(default=None, repr=False)


class TaskScheduler:
    """任务调度器。"""

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False

    def cron(
        self,
        name: str,
        interval_s: float,
    ) -> Callable:
        """装饰器：注册定时任务。"""

        def decorator(fn: Callable[[], Coroutine[Any, Any, None]]) -> Callable:
            self._tasks[name] = ScheduledTask(
                name=name, fn=fn, interval_s=interval_s
            )
            logger.info("scheduled task registered: %s (every %.0fs)", name, interval_s)
            return fn

        return decorator

    def schedule_once(
        self,
        name: str,
        fn: Callable[[], Coroutine[Any, Any, None]],
        delay_s: float = 0.0,
    ) -> None:
        """注册一次性延迟任务。"""
        self._tasks[name] = ScheduledTask(
            name=name, fn=fn, delay_s=delay_s
        )

    def cancel(self, name: str) -> bool:
        """取消任务。"""
        task = self._tasks.get(name)
        if not task:
            return False
        task.status = TaskStatus.CANCELLED
        if task._task and not task._task.done():
            task._task.cancel()
        return True

    async def start(self) -> None:
        """启动调度器。"""
        self._running = True
        logger.info("scheduler started with %d tasks", len(self._tasks))

        for name, task in self._tasks.items():
            if task.status == TaskStatus.CANCELLED:
                continue
            task._task = asyncio.create_task(self._run_task(task))

    async def stop(self) -> None:
        """停止调度器。"""
        self._running = False
        for task in self._tasks.values():
            if task._task and not task._task.done():
                task._task.cancel()
        logger.info("scheduler stopped")

    async def _run_task(self, task: ScheduledTask) -> None:
        """执行任务循环。"""
        # 初始延迟
        if task.delay_s > 0:
            await asyncio.sleep(task.delay_s)

        while self._running and task.status != TaskStatus.CANCELLED:
            task.status = TaskStatus.RUNNING
            task.last_run = time.time()

            try:
                await task.fn()
                task.run_count += 1
                task.status = TaskStatus.COMPLETED
            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                return
            except Exception as exc:
                task.error_count += 1
                task.last_error = str(exc)[:200]
                task.status = TaskStatus.FAILED
                logger.error("task %s failed: %s", task.name, exc)

            # 一次性任务不循环
            if task.interval_s is None:
                return

            task.next_run = time.time() + task.interval_s
            task.status = TaskStatus.PENDING
            await asyncio.sleep(task.interval_s)

    @property
    def status(self) -> dict[str, dict[str, Any]]:
        """所有任务状态。"""
        return {
            name: {
                "status": t.status.value,
                "run_count": t.run_count,
                "error_count": t.error_count,
                "last_run": t.last_run,
                "last_error": t.last_error,
                "interval_s": t.interval_s,
            }
            for name, t in self._tasks.items()
        }


# 全局单例
scheduler = TaskScheduler()
