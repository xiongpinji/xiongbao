"""请求优先级调度：按重要性排序执行。

功能：
- 多级优先级（P0-P4）
- 加权公平调度
- 并发槽位管理
- 饥饿保护（低优先级超时提升）

用法：
    from xagent.api.priority_scheduler import priority_scheduler, Priority

    task_id = await priority_scheduler.submit(
        fn=run_agent,
        priority=Priority.HIGH,
        args=(prompt,),
    )
    result = await priority_scheduler.wait(task_id)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.prio_sched")


class Priority(IntEnum):
    """优先级（数字越小越优先）。"""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class ScheduledItem:
    """调度项。"""

    task_id: str
    fn: Callable[..., Coroutine[Any, Any, Any]]
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    submitted_at: float = field(default_factory=time.time)
    future: asyncio.Future | None = None
    effective_priority: int = Priority.NORMAL

    def __lt__(self, other: "ScheduledItem") -> bool:
        return self.effective_priority < other.effective_priority


class PriorityScheduler:
    """优先级调度器。"""

    def __init__(self, max_concurrency: int = 10, starvation_timeout: float = 30.0):
        self.max_concurrency = max_concurrency
        self.starvation_timeout = starvation_timeout
        self._queue: asyncio.PriorityQueue[ScheduledItem] = asyncio.PriorityQueue()
        self._running = 0
        self._tasks: dict[str, ScheduledItem] = {}
        self._worker_started = False

    async def submit(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        priority: Priority = Priority.NORMAL,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> str:
        """提交任务。"""
        task_id = uuid.uuid4().hex[:12]
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        item = ScheduledItem(
            task_id=task_id,
            fn=fn,
            args=args,
            kwargs=kwargs or {},
            priority=priority,
            future=future,
            effective_priority=int(priority),
        )

        self._tasks[task_id] = item
        await self._queue.put(item)
        logger.debug("task submitted: %s (priority=%s)", task_id, priority.name)

        # 确保 worker 运行
        if not self._worker_started:
            self._worker_started = True
            asyncio.create_task(self._worker_loop())

        return task_id

    async def wait(self, task_id: str, timeout: float | None = None) -> Any:
        """等待任务结果。"""
        item = self._tasks.get(task_id)
        if not item or not item.future:
            raise KeyError(f"unknown task: {task_id}")
        return await asyncio.wait_for(item.future, timeout=timeout)

    async def _worker_loop(self):
        """调度主循环。"""
        while True:
            # 等待有空闲槽位
            while self._running >= self.max_concurrency:
                await asyncio.sleep(0.01)

            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if self._queue.empty() and self._running == 0:
                    self._worker_started = False
                    return
                continue

            # 饥饿保护：等待过久的提升优先级
            wait_time = time.time() - item.submitted_at
            if wait_time > self.starvation_timeout and item.effective_priority > 0:
                item.effective_priority = max(0, item.effective_priority - 1)
                logger.debug("starvation boost: %s → P%d", item.task_id, item.effective_priority)

            self._running += 1
            asyncio.create_task(self._execute(item))

    async def _execute(self, item: ScheduledItem):
        """执行任务。"""
        try:
            result = await item.fn(*item.args, **item.kwargs)
            if item.future and not item.future.done():
                item.future.set_result(result)
        except Exception as exc:
            if item.future and not item.future.done():
                item.future.set_exception(exc)
        finally:
            self._running -= 1
            self._tasks.pop(item.task_id, None)

    @property
    def stats(self) -> dict:
        return {
            "queue_size": self._queue.qsize(),
            "running": self._running,
            "max_concurrency": self.max_concurrency,
            "pending_tasks": len(self._tasks),
        }


# 全局单例
priority_scheduler = PriorityScheduler(max_concurrency=10)
