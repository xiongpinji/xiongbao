"""请求优先级队列：按优先级调度请求处理。

功能：
- 多级优先级（critical/high/normal/low/background）
- 并发控制
- 公平调度（同优先级 FIFO）
- 队列深度监控

用法：
    from xagent.api.priority_queue import PriorityQueueMiddleware

    app.add_middleware(PriorityQueueMiddleware, max_concurrent=20)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.priority_queue")


class Priority(IntEnum):
    """请求优先级。"""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class QueuedRequest:
    """排队中的请求。"""

    priority: Priority
    future: asyncio.Future
    path: str
    enqueued_at: float = field(default_factory=time.time)
    sequence: int = 0  # 同优先级排序


class RequestPriorityQueue:
    """请求优先级队列。"""

    def __init__(self, max_concurrent: int = 20, max_queue_size: int = 200):
        self._max_concurrent = max_concurrent
        self._max_queue_size = max_queue_size
        self._active = 0
        self._queue: list[QueuedRequest] = []
        self._sequence = 0
        self._lock = asyncio.Lock()

        # 统计
        self._total_enqueued = 0
        self._total_rejected = 0
        self._total_processed = 0

    async def acquire(self, priority: Priority, path: str) -> bool:
        """获取执行槽位。返回 True 表示可执行。"""
        async with self._lock:
            if self._active < self._max_concurrent:
                self._active += 1
                return True

            # 队列已满
            if len(self._queue) >= self._max_queue_size:
                self._total_rejected += 1
                return False

            # 入队等待
            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()
            self._sequence += 1
            self._queue.append(QueuedRequest(
                priority=priority,
                future=future,
                path=path,
                sequence=self._sequence,
            ))
            self._total_enqueued += 1

        # 等待槽位
        await future
        return True

    async def release(self) -> None:
        """释放执行槽位。"""
        async with self._lock:
            self._active -= 1
            self._total_processed += 1
            self._try_dequeue()

    def _try_dequeue(self) -> None:
        """尝试出队。"""
        if not self._queue or self._active >= self._max_concurrent:
            return

        # 按优先级+序列号排序
        self._queue.sort(key=lambda r: (r.priority, r.sequence))
        item = self._queue.pop(0)
        self._active += 1

        if not item.future.done():
            item.future.set_result(True)

    def get_stats(self) -> dict[str, Any]:
        """获取队列统计。"""
        return {
            "active": self._active,
            "queued": len(self._queue),
            "max_concurrent": self._max_concurrent,
            "total_enqueued": self._total_enqueued,
            "total_rejected": self._total_rejected,
            "total_processed": self._total_processed,
        }


# 全局队列
request_priority_queue = RequestPriorityQueue()


def _extract_priority(request: Request) -> Priority:
    """从请求中提取优先级。"""
    header = request.headers.get("x-priority", "normal").lower()
    mapping = {
        "critical": Priority.CRITICAL,
        "high": Priority.HIGH,
        "normal": Priority.NORMAL,
        "low": Priority.LOW,
        "background": Priority.BACKGROUND,
    }
    return mapping.get(header, Priority.NORMAL)


class PriorityQueueMiddleware(BaseHTTPMiddleware):
    """优先级队列中间件。"""

    def __init__(
        self,
        app,
        max_concurrent: int = 20,
        max_queue_size: int = 200,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.queue = RequestPriorityQueue(max_concurrent, max_queue_size)
        self.exclude_prefixes = exclude_prefixes or ["/health", "/ws"]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        priority = _extract_priority(request)
        acquired = await self.queue.acquire(priority, path)

        if not acquired:
            return JSONResponse(
                status_code=503,
                content={"error": "queue_full", "detail": "Server at capacity, try again later"},
                headers={"Retry-After": "10"},
            )

        try:
            response = await call_next(request)
            response.headers["X-Queue-Active"] = str(self.queue._active)
            return response
        finally:
            await self.queue.release()
