"""请求批处理：将多个小请求合并为批量调用。

功能：
- 时间窗口聚合
- 最大批量大小
- 按 key 分组
- 批量结果分发

用法：
    from xagent.api.request_batching import BatchProcessor

    async def process_batch(items: list[dict]) -> list[dict]:
        return [{"id": i["id"], "result": "ok"} for i in items]

    batcher = BatchProcessor(handler=process_batch, max_batch_size=50, window_ms=100)
    result = await batcher.submit({"id": "req-1", "data": "..."})
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.batching")


@dataclass
class BatchItem:
    """批次中的单项。"""

    data: Any
    future: asyncio.Future
    submitted_at: float = field(default_factory=time.time)


class BatchProcessor:
    """批处理器。"""

    def __init__(
        self,
        handler: Callable[[list[Any]], Coroutine[Any, Any, list[Any]]],
        max_batch_size: int = 50,
        window_ms: float = 100.0,
        max_wait_ms: float = 5000.0,
    ):
        self._handler = handler
        self._max_batch_size = max_batch_size
        self._window_ms = window_ms
        self._max_wait_ms = max_wait_ms

        self._queue: list[BatchItem] = []
        self._flush_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        # 统计
        self._total_submitted = 0
        self._total_batches = 0
        self._total_errors = 0

    async def submit(self, data: Any) -> Any:
        """提交单项，等待批处理结果。"""
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()

        async with self._lock:
            self._queue.append(BatchItem(data=data, future=future))
            self._total_submitted += 1

            # 达到批量大小立即刷新
            if len(self._queue) >= self._max_batch_size:
                await self._flush()
            elif self._flush_task is None or self._flush_task.done():
                # 启动窗口计时器
                self._flush_task = asyncio.create_task(self._window_timer())

        return await asyncio.wait_for(future, timeout=self._max_wait_ms / 1000)

    async def _window_timer(self) -> None:
        """等待窗口时间后刷新。"""
        await asyncio.sleep(self._window_ms / 1000)
        async with self._lock:
            await self._flush()

    async def _flush(self) -> None:
        """刷新当前队列。"""
        if not self._queue:
            return

        batch = self._queue[:self._max_batch_size]
        self._queue = self._queue[self._max_batch_size:]
        self._total_batches += 1

        items_data = [item.data for item in batch]

        try:
            results = await self._handler(items_data)

            # 分发结果
            for item, result in zip(batch, results):
                if not item.future.done():
                    item.future.set_result(result)

            logger.debug("batch processed: %d items", len(batch))

        except Exception as exc:
            self._total_errors += 1
            logger.error("batch processing failed: %s", exc)
            for item in batch:
                if not item.future.done():
                    item.future.set_exception(exc)

        # 如果还有剩余，继续处理
        if self._queue:
            await self._flush()

    def get_stats(self) -> dict[str, Any]:
        """获取统计。"""
        return {
            "total_submitted": self._total_submitted,
            "total_batches": self._total_batches,
            "total_errors": self._total_errors,
            "pending": len(self._queue),
            "avg_batch_size": (
                round(self._total_submitted / max(1, self._total_batches), 1)
            ),
        }

    async def shutdown(self) -> None:
        """关闭：刷新剩余。"""
        async with self._lock:
            await self._flush()
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
