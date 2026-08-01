"""优雅关闭：信号处理 + 连接排空。

功能：
- 捕获 SIGTERM / SIGINT 信号
- 等待进行中请求完成（排空期）
- 注册关闭钩子（数据库/缓存/队列清理）
- 超时强制退出

用法：
    from xagent.api.graceful_shutdown import shutdown_manager

    shutdown_manager.register_hook("close_db", close_database)
    shutdown_manager.register_hook("flush_cache", flush_redis)
    # 在 app lifespan 中：
    shutdown_manager.install_signal_handlers(loop)
    await shutdown_manager.wait_for_shutdown(timeout=30)
"""

from __future__ import annotations

import asyncio
import signal
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
    timeout: float = 10.0
    priority: int = 0  # 越小越先执行


@dataclass
class ShutdownState:
    """关闭状态。"""

    is_shutting_down: bool = False
    started_at: float = 0.0
    active_requests: int = 0
    hooks_completed: list[str] = field(default_factory=list)


class GracefulShutdownManager:
    """优雅关闭管理器。"""

    def __init__(self):
        self._hooks: list[ShutdownHook] = []
        self._state = ShutdownState()
        self._shutdown_event = asyncio.Event()
        self._active_requests = 0
        self._lock = asyncio.Lock()

    @property
    def is_shutting_down(self) -> bool:
        return self._state.is_shutting_down

    @property
    def active_requests(self) -> int:
        return self._active_requests

    def register_hook(
        self,
        name: str,
        fn: Callable[[], Coroutine[Any, Any, None]],
        timeout: float = 10.0,
        priority: int = 0,
    ) -> None:
        """注册关闭钩子。"""
        self._hooks.append(ShutdownHook(name=name, fn=fn, timeout=timeout, priority=priority))
        self._hooks.sort(key=lambda h: h.priority)
        logger.info("shutdown hook registered: %s (priority=%d)", name, priority)

    def install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """安装信号处理器。"""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._signal_handler, sig)
            except (NotImplementedError, RuntimeError):
                # Windows 不支持 add_signal_handler
                signal.signal(sig, lambda s, f: self._signal_handler(s))

    def _signal_handler(self, sig: Any) -> None:
        """信号触发关闭流程。"""
        sig_name = signal.Signals(sig).name if isinstance(sig, int) else str(sig)
        logger.warning("received signal %s, initiating graceful shutdown", sig_name)
        self._state.is_shutting_down = True
        self._state.started_at = time.time()
        self._shutdown_event.set()

    async def track_request_start(self) -> None:
        """请求开始计数。"""
        async with self._lock:
            self._active_requests += 1

    async def track_request_end(self) -> None:
        """请求结束计数。"""
        async with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    async def wait_for_shutdown(self, timeout: float = 30.0) -> None:
        """等待关闭信号并执行清理。"""
        await self._shutdown_event.wait()
        await self._drain_and_cleanup(timeout)

    async def _drain_and_cleanup(self, timeout: float) -> None:
        """排空请求 + 执行钩子。"""
        deadline = time.time() + timeout

        # 1. 等待活跃请求完成
        logger.info("draining %d active requests...", self._active_requests)
        while self._active_requests > 0 and time.time() < deadline:
            await asyncio.sleep(0.1)

        if self._active_requests > 0:
            logger.warning(
                "force shutdown: %d requests still active", self._active_requests
            )

        # 2. 执行关闭钩子
        for hook in self._hooks:
            remaining = deadline - time.time()
            if remaining <= 0:
                logger.warning("shutdown timeout, skipping hook: %s", hook.name)
                continue
            try:
                hook_timeout = min(hook.timeout, remaining)
                await asyncio.wait_for(hook.fn(), timeout=hook_timeout)
                self._state.hooks_completed.append(hook.name)
                logger.info("shutdown hook completed: %s", hook.name)
            except asyncio.TimeoutError:
                logger.error("shutdown hook timeout: %s", hook.name)
            except Exception as exc:
                logger.error("shutdown hook failed: %s — %s", hook.name, exc)

        elapsed = time.time() - self._state.started_at
        logger.info("graceful shutdown complete (%.1fs)", elapsed)

    async def trigger_shutdown(self) -> None:
        """手动触发关闭（测试/管理端点用）。"""
        self._signal_handler(signal.SIGTERM)


# 全局单例
shutdown_manager = GracefulShutdownManager()
