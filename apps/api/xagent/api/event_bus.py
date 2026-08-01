"""事件总线：进程内异步事件发布/订阅。

功能：
- 主题发布/订阅
- 异步处理器
- 通配符订阅
- 错误隔离

用法：
    from xagent.api.event_bus import event_bus

    @event_bus.subscribe("user.created")
    async def on_user_created(event: dict):
        ...

    await event_bus.publish("user.created", {"user_id": "u1"})
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.event_bus")

Handler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


@dataclass
class Subscription:
    """订阅。"""

    topic: str
    handler: Handler
    name: str = ""
    created_at: float = field(default_factory=time.time)


class EventBus:
    """异步事件总线。"""

    def __init__(self, max_history: int = 500):
        self._subscribers: dict[str, list[Subscription]] = defaultdict(list)
        self._history: list[dict[str, Any]] = []
        self._max_history = max_history
        self._total_published = 0
        self._total_errors = 0

    def subscribe(self, topic: str, name: str = ""):
        """订阅装饰器。"""

        def decorator(fn: Handler) -> Handler:
            self._subscribers[topic].append(Subscription(
                topic=topic,
                handler=fn,
                name=name or fn.__name__,
            ))
            logger.debug("subscribed: %s → %s", topic, name or fn.__name__)
            return fn

        return decorator

    def add_subscriber(self, topic: str, handler: Handler, name: str = "") -> None:
        """手动添加订阅。"""
        self._subscribers[topic].append(Subscription(
            topic=topic,
            handler=handler,
            name=name or handler.__name__,
        ))

    def remove_subscriber(self, topic: str, handler: Handler) -> None:
        """移除订阅。"""
        subs = self._subscribers.get(topic, [])
        self._subscribers[topic] = [s for s in subs if s.handler is not handler]

    async def publish(self, topic: str, data: dict[str, Any] | None = None) -> int:
        """发布事件。返回处理的订阅数。"""
        event = {
            "topic": topic,
            "data": data or {},
            "timestamp": time.time(),
        }
        self._total_published += 1
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # 收集匹配的订阅者
        handlers: list[Subscription] = []
        handlers.extend(self._subscribers.get(topic, []))
        # 通配符
        handlers.extend(self._subscribers.get("*", []))
        # 前缀通配（如 "user.*"）
        prefix = topic.rsplit(".", 1)[0] + ".*" if "." in topic else ""
        if prefix:
            handlers.extend(self._subscribers.get(prefix, []))

        if not handlers:
            return 0

        # 并行执行
        tasks = [self._safe_call(sub, event) for sub in handlers]
        await asyncio.gather(*tasks)

        return len(handlers)

    async def _safe_call(self, sub: Subscription, event: dict[str, Any]) -> None:
        """安全调用处理器。"""
        try:
            await sub.handler(event)
        except Exception as exc:
            self._total_errors += 1
            logger.error(
                "event handler error: topic=%s handler=%s error=%s",
                sub.topic, sub.name, exc,
            )

    def get_history(self, topic: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """获取事件历史。"""
        if topic:
            filtered = [e for e in self._history if e["topic"] == topic]
            return filtered[-limit:]
        return self._history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """获取统计。"""
        return {
            "topics": len(self._subscribers),
            "total_subscribers": sum(len(v) for v in self._subscribers.values()),
            "total_published": self._total_published,
            "total_errors": self._total_errors,
        }

    def list_topics(self) -> list[str]:
        """列出所有主题。"""
        return list(self._subscribers.keys())


# 全局实例
event_bus = EventBus()
