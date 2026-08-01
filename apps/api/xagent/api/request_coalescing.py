"""请求合并：相同请求只执行一次，共享结果。

功能：
- 相同 key 的并发请求合并为一次执行
- 结果共享给所有等待者
- 自动过期清理

用法：
    from xagent.api.request_coalescing import coalesce

    @coalesce(key_fn=lambda user_id: f"user:{user_id}")
    async def get_user(user_id: str) -> dict:
        ...
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.coalescing")


@dataclass
class InflightRequest:
    """进行中的请求。"""

    future: asyncio.Future
    started_at: float = field(default_factory=time.time)
    waiters: int = 1


class RequestCoalescer:
    """请求合并器。"""

    def __init__(self, ttl_s: float = 5.0):
        self._inflight: dict[str, InflightRequest] = {}
        self._cache: dict[str, tuple[Any, float]] = {}
        self._ttl_s = ttl_s
        self._total_coalesced = 0
        self._total_executed = 0

    async def execute(
        self,
        key: str,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """执行或合并请求。"""
        # 检查缓存
        cached = self._cache.get(key)
        if cached and time.time() - cached[1] < self._ttl_s:
            return cached[0]

        # 检查进行中
        inflight = self._inflight.get(key)
        if inflight:
            inflight.waiters += 1
            self._total_coalesced += 1
            logger.debug("coalesced: key=%s waiters=%d", key, inflight.waiters)
            return await inflight.future

        # 首次执行
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._inflight[key] = InflightRequest(future=future)
        self._total_executed += 1

        try:
            result = await fn(*args, **kwargs)
            future.set_result(result)
            self._cache[key] = (result, time.time())
            return result
        except Exception as exc:
            future.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)

    def invalidate(self, key: str) -> None:
        """使缓存失效。"""
        self._cache.pop(key, None)

    def invalidate_all(self) -> None:
        """清空缓存。"""
        self._cache.clear()

    def get_stats(self) -> dict[str, Any]:
        return {
            "inflight": len(self._inflight),
            "cached": len(self._cache),
            "total_coalesced": self._total_coalesced,
            "total_executed": self._total_executed,
            "coalesce_rate": round(
                self._total_coalesced / max(1, self._total_coalesced + self._total_executed), 3
            ),
        }


# 全局实例
request_coalescer = RequestCoalescer()


def coalesce(key_fn: Callable[..., str] | None = None, ttl_s: float = 5.0):
    """合并装饰器。"""

    def decorator(fn: Callable[..., Coroutine[Any, Any, Any]]):
        coalescer = RequestCoalescer(ttl_s=ttl_s)

        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if key_fn:
                key = key_fn(*args, **kwargs)
            else:
                key = f"{fn.__name__}:{args}:{kwargs}"
            return await coalescer.execute(key, fn, *args, **kwargs)

        wrapper.__name__ = fn.__name__
        wrapper.coalescer = coalescer
        return wrapper

    return decorator
