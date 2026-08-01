"""请求合并窗口：时间窗口内合并同类操作。

功能：
- 滑动时间窗口收集操作
- 窗口关闭后批量执行
- 按 key 分组合并
- 每个提交者获得独立结果

用法：
    from xagent.api.merge_window import merge_window

    @merge_window.register("notifications", window_ms=200, max_batch=50)
    async def send_notifications(items: list[dict]) -> list[bool]:
        return await notification_service.batch_send(items)

    # 调用方（自动合并）：
    result = await merge_window.submit("notifications", {"user": "u1", "msg": "hello"})
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.merge_window")


@dataclass
class PendingItem:
    """窗口中的待处理项。"""

    data: Any
    future: asyncio.Future
    submitted_at: float = field(default_factory=time.time)


@dataclass
class WindowConfig:
    """窗口配置。"""

    name: str
    handler: Callable[[list[Any]], Coroutine[Any, Any, list[Any]]]
    window_ms: float = 100
    max_batch: int = 100


class MergeWindowManager:
    """合并窗口管理器。"""

    def __init__(self):
        self._configs: dict[str, WindowConfig] = {}
        self._buffers: dict[str, list[PendingItem]] = {}
        self._timers: dict[str, asyncio.TimerHandle | None] = {}
        self._flushing: dict[str, bool] = {}

    def register(
        self,
        name: str,
        window_ms: float = 100,
        max_batch: int = 100,
    ):
        """注册合并窗口（装饰器）。"""

        def decorator(fn: Callable[[list[Any]], Coroutine[Any, Any, list[Any]]]):
            self._configs[name] = WindowConfig(
                name=name, handler=fn, window_ms=window_ms, max_batch=max_batch
            )
            self._buffers[name] = []
            self._timers[name] = None
            self._flushing[name] = False
            return fn

        return decorator

    async def submit(self, name: str, data: Any) -> Any:
        """提交数据到窗口。"""
        config = self._configs.get(name)
        if not config:
            raise KeyError(f"unknown merge window: {name}")

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        item = PendingItem(data=data, future=future)
        self._buffers[name].append(item)

        # 达到批次上限立即刷新
        if len(self._buffers[name]) >= config.max_batch:
            await self._flush(name)
        elif self._timers[name] is None:
            # 启动窗口计时器
            self._timers[name] = loop.call_later(
                config.window_ms / 1000,
                lambda: asyncio.ensure_future(self._flush(name)),
            )

        return await future

    async def _flush(self, name: str) -> None:
        """刷新窗口。"""
        if self._flushing.get(name):
            return

        self._flushing[name] = True

        # 取消计时器
        if self._timers.get(name):
            self._timers[name].cancel()
            self._timers[name] = None

        # 取出缓冲
        items = self._buffers[name]
        self._buffers[name] = []

        if not items:
            self._flushing[name] = False
            return

        config = self._configs[name]
        data_list = [item.data for item in items]

        try:
            results = await config.handler(data_list)
            # 分发结果
            for i, item in enumerate(items):
                if i < len(results):
                    item.future.set_result(results[i])
                else:
                    item.future.set_result(None)
            logger.debug("merge window flushed: %s (%d items)", name, len(items))
        except Exception as exc:
            for item in items:
                if not item.future.done():
                    item.future.set_exception(exc)
        finally:
            self._flushing[name] = False

    @property
    def stats(self) -> dict:
        return {
            name: {"buffered": len(self._buffers.get(name, []))}
            for name in self._configs
        }


# 全局单例
merge_window = MergeWindowManager()
