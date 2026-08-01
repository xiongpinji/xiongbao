"""请求合并与去重：减少重复调用 + 批量合并。

功能：
- 相同请求去重（in-flight dedup）：并发相同请求只执行一次
- 请求合并（batching）：短时间窗口内的请求合并为一次批量调用
- 结果共享：所有等待者共享同一结果

用法：
    from xagent.api.request_dedup import dedup, RequestBatcher

    # 去重：相同 key 的并发调用只执行一次
    @dedup(key_fn=lambda user_id: f"user:{user_id}")
    async def get_user(user_id: str) -> dict: ...

    # 合并：50ms 窗口内的 ID 合并为一次批量查询
    batcher = RequestBatcher(batch_fn=batch_get_users, window_ms=50)
    user = await batcher.request("user-123")
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Hashable, TypeVar

from xagent.infra.logging import get_logger

logger = get_logger("xagent.dedup")

T = TypeVar("T")


# ─── 请求去重 ───


class InflightDedup:
    """In-flight 请求去重器。

    相同 key 的并发请求只执行一次，其余等待共享结果。
    """

    def __init__(self):
        self._inflight: dict[Hashable, asyncio.Future] = {}
        self._stats = {"hits": 0, "misses": 0}

    async def execute(
        self,
        key: Hashable,
        fn: Callable[..., Coroutine],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """执行或等待已有结果。"""
        if key in self._inflight:
            self._stats["hits"] += 1
            logger.debug("dedup hit: %s", key)
            return await self._inflight[key]

        self._stats["misses"] += 1
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._inflight[key] = future

        try:
            result = await fn(*args, **kwargs)
            future.set_result(result)
            return result
        except Exception as exc:
            future.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)

    @property
    def stats(self) -> dict:
        return {**self._stats, "inflight": len(self._inflight)}


# 全局去重器
_dedup_instance: InflightDedup | None = None


def get_dedup() -> InflightDedup:
    global _dedup_instance
    if _dedup_instance is None:
        _dedup_instance = InflightDedup()
    return _dedup_instance


def dedup(key_fn: Callable[..., Hashable]):
    """去重装饰器。

    用法：
        @dedup(key_fn=lambda uid: f"user:{uid}")
        async def get_user(uid: str) -> dict: ...
    """

    def decorator(fn: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = key_fn(*args, **kwargs)
            return await get_dedup().execute(key, fn, *args, **kwargs)

        return wrapper

    return decorator


# ─── 请求合并（Batching） ───


@dataclass
class _PendingItem:
    """等待合并的单项。"""

    item: Any
    future: asyncio.Future
    enqueued_at: float = field(default_factory=time.time)


class RequestBatcher:
    """请求合并器：时间窗口内收集请求，一次性批量执行。

    适用于：根据 ID 列表批量查询数据库 / 外部 API。
    """

    def __init__(
        self,
        batch_fn: Callable[[list[Any]], Coroutine[Any, Any, list[Any]]],
        window_ms: int = 50,
        max_batch_size: int = 100,
    ):
        """
        Args:
            batch_fn: 批量执行函数，接收 item 列表，返回对应结果列表
            window_ms: 合并窗口（毫秒）
            max_batch_size: 单批最大数量
        """
        self._batch_fn = batch_fn
        self._window_ms = window_ms
        self._max_batch_size = max_batch_size
        self._pending: list[_PendingItem] = []
        self._timer: asyncio.TimerHandle | None = None
        self._stats = {"batches": 0, "items": 0}

    async def request(self, item: Any) -> Any:
        """提交单项请求，等待合并执行后返回对应结果。"""
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending.append(_PendingItem(item=item, future=future))

        # 达到最大批量立即触发
        if len(self._pending) >= self._max_batch_size:
            await self._flush()
        elif self._timer is None:
            # 启动窗口计时器
            self._timer = loop.call_later(
                self._window_ms / 1000,
                lambda: asyncio.ensure_future(self._flush()),
            )

        return await future

    async def _flush(self) -> None:
        """执行批量请求。"""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

        if not self._pending:
            return

        batch = self._pending[: self._max_batch_size]
        self._pending = self._pending[self._max_batch_size :]

        items = [p.item for p in batch]
        self._stats["batches"] += 1
        self._stats["items"] += len(items)

        try:
            results = await self._batch_fn(items)
            for pending, result in zip(batch, results):
                if not pending.future.done():
                    pending.future.set_result(result)
        except Exception as exc:
            for pending in batch:
                if not pending.future.done():
                    pending.future.set_exception(exc)

        # 如果还有剩余，继续下一批
        if self._pending:
            await self._flush()

    @property
    def stats(self) -> dict:
        return {**self._stats, "pending": len(self._pending)}
