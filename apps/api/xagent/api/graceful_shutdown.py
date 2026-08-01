"""优雅关闭：服务停机时有序清理资源。

功能：
- 注册关闭钩子（按优先级）
- 停止接收新请求
- 等待进行中请求完成
- 超时强制关闭

用法：
    from xagent.api.graceful_shutdown import shutdown_manager

    shutdown_manager.register("close_db", close_database, priority=10)
    shutdown_manager.register("flush_logs", flush_logs, priority=1)

    # 在信号处理中：
    await shutdown_manager.shutdown(timeout_s=30)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.shutdown")


@dataclass
class ShutdownHook:
    """关闭钩子。"""

    name: str
    fn: Callable[[], Coroutine[Any, Any, None]]
    priority: int = 0  # 越小越先执行
    timeout_s: float = 10.0
    registered_at: float = field(default_factory=time.time)


class GracefulShutdownManager:
    """优雅关闭管理器。"""

    def __init__(self):
        self._hooks: list[ShutdownHook] = []
        self._shutting_down = False
        self._active_requests = 0
        self._lock = asyncio.Lock()

    def register(
        self,
        name: str,
        fn: Callable[[], Coroutine[Any, Any, None]],
        priority: int = 0,
        timeout_s: float = 10.0,
    ) -> None:
        """注册关闭钩子。"""
        self._hooks.append(ShutdownHook(name=name, fn=fn, priority=priority, timeout_s=timeout_s))
        self._hooks.sort(key=lambda h: h.priority)
        logger.info("shutdown hook registered: %s (priority=%d)", name, priority)

    def unregister(self, name: str) -> None:
        """注销钩子。"""
        self._hooks = [h for h in self._hooks if h.name != name]

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    async def track_request_start(self) -> bool:
        """追踪请求开始。返回 False 表示正在关闭。"""
        if self._shutting_down:
            return False
        async with self._lock:
            self._active_requests += 1
        return True

    async def track_request_end(self) -> None:
        """追踪请求结束。"""
        async with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    async def shutdown(self, timeout_s: float = 30.0) -> dict[str, Any]:
        """执行优雅关闭。"""
        self._shutting_down = True
        start = time.time()
        results: list[dict[str, Any]] = []

        logger.info("graceful shutdown initiated (timeout=%.1fs)", timeout_s)

        # 等待进行中请求
        drain_deadline = start + min(timeout_s * 0.5, 15)
        while self._active_requests > 0 and time.time() < drain_deadline:
            await asyncio.sleep(0.1)

        if self._active_requests > 0:
            logger.warning("drain timeout: %d requests still active", self._active_requests)

        # 执行钩子
        for hook in self._hooks:
            elapsed = time.time() - start
            remaining = timeout_s - elapsed
            if remaining <= 0:
                results.append({"name": hook.name, "status": "skipped", "reason": "timeout"})
                continue

            hook_start = time.time()
            try:
                await asyncio.wait_for(hook.fn(), timeout=min(hook.timeout_s, remaining))
                results.append({
                    "name": hook.name,
                    "status": "ok",
                    "duration_ms": round((time.time() - hook_start) * 1000, 1),
                })
                logger.info("shutdown hook ok: %s", hook.name)
            except asyncio.TimeoutError:
                results.append({"name": hook.name, "status": "timeout"})
                logger.warning("shutdown hook timeout: %s", hook.name)
            except Exception as exc:
                results.append({"name": hook.name, "status": "error", "error": str(exc)[:200]})
                logger.error("shutdown hook error: %s: %s", hook.name, exc)

        total_time = time.time() - start
        logger.info("graceful shutdown complete in %.1fs", total_time)

        return {
            "total_time_s": round(total_time, 2),
            "hooks": results,
            "remaining_requests": self._active_requests,
        }


# 全局实例
shutdown_manager = GracefulShutdownManager()
