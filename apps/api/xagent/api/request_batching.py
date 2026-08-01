"""请求合并：将短时间内的多个请求合并为一次批量处理。

功能：
- 时间窗口内收集请求（默认 50ms）
- 达到批次大小或超时后统一执行
- 每个请求独立获得结果
- 支持最大批次限制

用法：
    from xagent.api.request_batching import batch_processor

    @batch_processor.register("embeddings", max_batch=32, window_ms=50)
    async def process_embeddings(items: list[str]) -> list[list[float]]:
        return await embedding_api.batch_embed(items)

    # 调用方：
    result = await batch_processor.submit("embeddings", "hello world")
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
    """批次中的单个请求。"""

    data: Any
    future: asyncio.Future
    enqueued_at: float = field(default_factory=time.time)


@dataclass
class BatchConfig:
    """批次配置。"""

    name: str
    handler: Callable[[list[Any]], Coroutine[Any, Any, list[Any]]]
    max_batch: int = 32
    window_ms: float = 50.0
    max_wait_ms: float = 200.0


class BatchProcessor:
    """请求合并处理器。"""

    def __init__(self):
        self._configs: dict[str, BatchConfig] = {}
        self._queues: dict[str, list[BatchItem]] = {}
        self._timers: dict[str, asyncio.Task | None] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._stats: dict[str, dict[str, int]] = {}

    def register(
        self,
        name: str,
        max_batch: int = 32,
        window_ms: float = 50.0,
        max_wait_ms: float = 200.0,
    ) -> Callable:
        """装饰器：注册批处理函数。"""

        def decorator(
            fn: Callable[[list[Any]], Coroutine[Any, Any, list[Any]]],
        ) -> Callable:
            self._configs[name] = BatchConfig(
                name=name,
                handler=fn,
                max_batch=max_batch,
                window_ms=window_ms,
                max_wait_ms=max_wait_ms,
            )
            self._queues[name] = []
            self._locks[name] = asyncio.Lock()
            self._stats[name] = {"batches": 0, "items": 0, "errors": 0}
            return fn

        return decorator

    async def submit(self, name: str, data: Any) -> Any:
        """提交单个请求到批次。"""
        config = self._configs.get(name)
        if not config:
            raise ValueError(f"Unknown batch processor: {name}")

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        item = BatchItem(data=data, future=future)

        async with self._locks[name]:
            self._queues[name].append(item)
            queue_size = len(self._queues[name])

            # 达到批次大小 → 立即触发
            if queue_size >= config.max_batch:
                await self._flush(name)
            # 首个请求 → 启动窗口计时器
            elif queue_size == 1:
                self._timers[name] = asyncio.create_task(
                    self._window_timer(name, config.window_ms / 1000)
                )

        return await future

    async def _window_timer(self, name: str, window_s: float) -> None:
        """窗口计时器到期后刷新批次。"""
        await asyncio.sleep(window_s)
        async with self._locks[name]:
            if self._queues[name]:
                await self._flush(name)

    async def _flush(self, name: str) -> None:
        """执行当前批次。"""
        config = self._configs[name]
        batch = self._queues[name][: config.max_batch]
        self._queues[name] = self._queues[name][config.max_batch :]

        if not batch:
            return

        # 取消计时器
        timer = self._timers.get(name)
        if timer and not timer.done():
            timer.cancel()
        self._timers[name] = None

        self._stats[name]["batches"] += 1
        self._stats[name]["items"] += len(batch)

        try:
            items_data = [item.data for item in batch]
            results = await config.handler(items_data)

            if len(results) != len(batch):
                raise ValueError(
                    f"Handler returned {len(results)} results for {len(batch)} items"
                )

            for item, result in zip(batch, results):
                if not item.future.done():
                    item.future.set_result(result)

        except Exception as exc:
            self._stats[name]["errors"] += 1
            logger.error("batch %s failed: %s", name, exc)
            for item in batch:
                if not item.future.done():
                    item.future.set_exception(exc)

    @property
    def stats(self) -> dict[str, dict[str, int]]:
        return self._stats


# 全局单例
batch_processor = BatchProcessor()
