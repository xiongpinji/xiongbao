"""请求去重合并：相同请求共享结果。

功能：
- 相同参数的并发请求只执行一次
- 后续请求等待首个结果
- 自动过期清理
- 装饰器/手动两种模式

用法：
    from xagent.api.dedup_merge import dedup

    @dedup(key_fn=lambda user_id: f"user:{user_id}", ttl=5.0)
    async def get_user(user_id: str) -> dict:
        return await db.fetch_user(user_id)

    # 并发调用 get_user("u1") 只会执行一次 DB 查询
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.dedup")


@dataclass
class PendingCall:
    """进行中的调用。"""

    future: asyncio.Future
    created_at: float = field(default_factory=time.time)
    waiters: int = 0


class DedupManager:
    """请求去重管理器。"""

    def __init__(self, default_ttl: float = 10.0):
        self.default_ttl = default_ttl
        self._pending: dict[str, PendingCall] = {}
        self._results: dict[str, tuple[Any, float]] = {}  # key → (result, expire_at)

    async def execute(
        self,
        key: str,
        fn: Callable[[], Coroutine[Any, Any, Any]],
        ttl: float | None = None,
    ) -> Any:
        """去重执行。"""
        ttl = ttl or self.default_ttl

        # 检查缓存结果
        if key in self._results:
            result, expire_at = self._results[key]
            if time.time() < expire_at:
                return result
            del self._results[key]

        # 检查进行中的调用
        if key in self._pending:
            pending = self._pending[key]
            pending.waiters += 1
            logger.debug("dedup join: %s (waiters=%d)", key, pending.waiters)
            return await pending.future

        # 首个调用
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[key] = PendingCall(future=future)

        try:
            result = await fn()
            future.set_result(result)
            # 缓存结果
            self._results[key] = (result, time.time() + ttl)
            return result
        except Exception as exc:
            future.set_exception(exc)
            raise
        finally:
            del self._pending[key]

    def invalidate(self, key: str) -> None:
        """使缓存失效。"""
        self._results.pop(key, None)

    def clear(self) -> None:
        """清空所有缓存。"""
        self._results.clear()

    @property
    def stats(self) -> dict:
        return {
            "pending": len(self._pending),
            "cached": len(self._results),
        }


# 全局实例
dedup_manager = DedupManager()


def dedup(
    key_fn: Callable[..., str] | None = None,
    ttl: float = 10.0,
):
    """去重装饰器。"""

    def decorator(fn: Callable[..., Coroutine[Any, Any, Any]]):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if key_fn:
                key = key_fn(*args, **kwargs)
            else:
                key = f"{fn.__module__}.{fn.__qualname__}:{args}:{kwargs}"

            async def call():
                return await fn(*args, **kwargs)

            return await dedup_manager.execute(key, call, ttl=ttl)

        return wrapper

    return decorator
