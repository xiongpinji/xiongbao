"""请求优先级队列：按优先级调度异步任务。

功能：
- 多级优先级（critical > high > normal > low）
- 同优先级 FIFO
- 并发控制
- 队列状态监控

用法：
    from xagent.api.priority_queue import PriorityQueueManager, Priority

    pq = PriorityQueueManager(max_concurrent=3)
    await pq.submit(my_task, priority=Priority.HIGH, args=(arg1,))
"""

from __future__ import annotations

import asyncio
import heapq
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.priority_queue")


class Priority(IntEnum):
    """优先级（数值越小越优先）。"""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass(order=True)
class PriorityItem:
    """优先级队列项。"""

    priority: int
    sequence: int  # 同优先级 FIFO
    task_id: str = field(compare=False)
    fn: Callable = field(compare=False)
    args: tuple = field(compare=False, default=())
    kwargs: dict = field(compare=False, default_factory=dict)
    future: asyncio.Future = field(compare=False, default=None)
    enqueued_at: float = field(compare=False, default_factory=time.time)


class PriorityQueueManager:
    """优先级任务队列。"""

    def __init__(self, max_concurrent: int = 5):
        self._queue: list[PriorityItem] = []
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._sequence = 0
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._stats = {"submitted": 0, "completed": 0, "failed": 0}

    async def start(self) -> None:
        """启动队列处理器。"""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._process_loop())
        logger.info("priority queue started (max_concurrent=%d)", self._semaphore._value)

    async def stop(self) -> None:
        """停止队列。"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def submit(
        self,
        fn: Callable[..., Coroutine],
        *,
        priority: Priority = Priority.NORMAL,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> str:
        """提交任务到队列。"""
        task_id = str(uuid.uuid4())[:8]
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        item = PriorityItem(
            priority=priority.value,
            sequence=self._sequence,
            task_id=task_id,
            fn=fn,
            args=args,
            kwargs=kwargs or {},
            future=future,
        )
        self._sequence += 1

        heapq.heappush(self._queue, item)
        self._stats["submitted"] += 1

        logger.debug(
            "task submitted: %s (priority=%s, queue_size=%d)",
            task_id,
            priority.name,
            len(self._queue),
        )

        return task_id

    async def _process_loop(self) -> None:
        """主处理循环。"""
        while self._running:
            if not self._queue:
                await asyncio.sleep(0.05)
                continue

            item = heapq.heappop(self._queue)
            asyncio.create_task(self._execute(item))

    async def _execute(self, item: PriorityItem) -> None:
        """执行单个任务。"""
        async with self._semaphore:
            try:
                result = await item.fn(*item.args, **item.kwargs)
                if not item.future.done():
                    item.future.set_result(result)
                self._stats["completed"] += 1
            except Exception as exc:
                if not item.future.done():
                    item.future.set_exception(exc)
                self._stats["failed"] += 1
                logger.warning("task failed: %s - %s", item.task_id, exc)

    @property
    def stats(self) -> dict:
        return {
            **self._stats,
            "queue_size": len(self._queue),
            "running": self._running,
        }
