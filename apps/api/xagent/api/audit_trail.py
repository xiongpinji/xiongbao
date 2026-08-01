"""审计日志：操作追踪与合规记录。

功能：
- 记录关键操作（创建/修改/删除/登录）
- 结构化审计事件（who / what / when / where）
- 变更差异（before / after）
- 异步写入不阻塞请求
- 查询接口

用法：
    from xagent.api.audit_trail import audit

    await audit.log(
        action="agent.update",
        user_id="u123",
        resource_type="agent",
        resource_id="a456",
        changes={"name": {"before": "old", "after": "new"}},
        ip="1.2.3.4",
    )
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.audit")


class AuditAction(str, Enum):
    """审计动作类型。"""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    IMPORT = "import"
    EXECUTE = "execute"


@dataclass
class AuditEvent:
    """审计事件。"""

    id: str
    action: str
    user_id: str | None
    resource_type: str
    resource_id: str | None
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    ip: str | None = None
    user_agent: str | None = None
    timestamp: float = field(default_factory=time.time)
    trace_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "changes": self.changes,
            "metadata": self.metadata,
            "ip": self.ip,
            "user_agent": self.user_agent,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
        }


class AuditTrail:
    """审计日志管理器。

    内存存储（生产环境应替换为数据库写入）。
    异步队列写入，不阻塞主请求。
    """

    def __init__(self, max_events: int = 10000):
        self._events: deque[AuditEvent] = deque(maxlen=max_events)
        self._queue: asyncio.Queue[AuditEvent] = asyncio.Queue(maxsize=1000)
        self._writer_task: asyncio.Task | None = None
        self._running = False
        self._stats = {"logged": 0, "dropped": 0}

    async def start(self) -> None:
        """启动后台写入任务。"""
        if self._running:
            return
        self._running = True
        self._writer_task = asyncio.create_task(self._writer_loop())
        logger.info("audit trail writer started")

    async def stop(self) -> None:
        """停止写入。"""
        self._running = False
        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
        logger.info("audit trail writer stopped")

    async def log(
        self,
        action: str,
        user_id: str | None = None,
        resource_type: str = "unknown",
        resource_id: str | None = None,
        changes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> str:
        """记录审计事件（非阻塞）。"""
        event = AuditEvent(
            id=str(uuid.uuid4())[:8],
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes,
            metadata=metadata or {},
            ip=ip,
            user_agent=user_agent,
            trace_id=trace_id,
        )

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._stats["dropped"] += 1
            logger.warning("audit queue full, event dropped: %s", action)

        return event.id

    async def _writer_loop(self) -> None:
        """后台消费队列。"""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                self._events.append(event)
                self._stats["logged"] += 1
                logger.debug(
                    "audit: %s %s/%s by %s",
                    event.action,
                    event.resource_type,
                    event.resource_id,
                    event.user_id,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def query(
        self,
        action: str | None = None,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """查询审计记录。"""
        results = []
        for event in reversed(self._events):  # 最新在前
            if action and event.action != action:
                continue
            if user_id and event.user_id != user_id:
                continue
            if resource_type and event.resource_type != resource_type:
                continue
            if resource_id and event.resource_id != resource_id:
                continue
            results.append(event.to_dict())

        return results[offset : offset + limit]

    @property
    def stats(self) -> dict:
        return {
            **self._stats,
            "stored": len(self._events),
            "queue_size": self._queue.qsize(),
        }


# 全局单例
audit = AuditTrail()


def compute_changes(before: dict, after: dict) -> dict[str, dict]:
    """计算两个字典的差异。

    返回：{"field": {"before": old, "after": new}}
    """
    changes = {}
    all_keys = set(before.keys()) | set(after.keys())

    for key in all_keys:
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val != new_val:
            changes[key] = {"before": old_val, "after": new_val}

    return changes
