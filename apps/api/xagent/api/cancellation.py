"""请求取消管理：AbortController 统一管控。

功能：
- 为每个请求分配 AbortController
- 组件卸载时自动取消进行中请求
- 支持按 key 取消 / 全部取消
- 防止竞态（新请求取消旧请求）

用法（前端）：
    const { getSignal, cancelAll, cancelByKey } = useAbortController();
    const data = await fetch("/api", { signal: getSignal("list") });
"""

from __future__ import annotations

# ─── 后端：请求取消追踪器 ───

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CancelableTask:
    """可取消的异步任务。"""

    key: str
    task: asyncio.Task
    created_at: float = field(default_factory=lambda: __import__("time").time())


class RequestCancellationManager:
    """后端请求取消管理器。

    用于长时间运行的任务（Agent 对话、批量处理），
    允许客户端通过 API 取消进行中的请求。
    """

    def __init__(self):
        self._tasks: dict[str, CancelableTask] = {}

    def register(self, key: str, task: asyncio.Task) -> None:
        """注册可取消任务。"""
        # 如果同 key 已有任务，先取消旧的
        if key in self._tasks:
            self._tasks[key].task.cancel()
        self._tasks[key] = CancelableTask(key=key, task=task)

        # 任务完成后自动清理
        task.add_done_callback(lambda _: self._tasks.pop(key, None))

    def cancel(self, key: str) -> bool:
        """取消指定任务。"""
        entry = self._tasks.get(key)
        if entry and not entry.task.done():
            entry.task.cancel()
            return True
        return False

    def cancel_all(self) -> int:
        """取消所有任务，返回取消数量。"""
        count = 0
        for entry in self._tasks.values():
            if not entry.task.done():
                entry.task.cancel()
                count += 1
        return count

    def is_running(self, key: str) -> bool:
        """检查任务是否运行中。"""
        entry = self._tasks.get(key)
        return entry is not None and not entry.task.done()

    @property
    def active_keys(self) -> list[str]:
        """当前活跃的任务 key。"""
        return [k for k, v in self._tasks.items() if not v.task.done()]

    @property
    def stats(self) -> dict:
        return {
            "active": len(self.active_keys),
            "keys": self.active_keys,
        }


# 单例
_manager: RequestCancellationManager | None = None


def get_cancellation_manager() -> RequestCancellationManager:
    global _manager
    if _manager is None:
        _manager = RequestCancellationManager()
    return _manager
