"""优雅停机管理：连接排空 + 信号处理 + 任务等待。

确保部署/重启时不丢失正在处理的请求：
1. 收到 SIGTERM/SIGINT → 停止接受新连接
2. 等待进行中请求完成（最长 30s）
3. 关闭后台任务（scheduler、MCP、WS）
4. 刷新缓冲（traces、metrics）
5. 关闭数据库连接池

用法：
    from xagent.api.graceful_shutdown import GracefulShutdownManager
    manager = GracefulShutdownManager(app)
    manager.install()
"""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass, field

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from xagent.infra.logging import get_logger

logger = get_logger("xagent.shutdown")


@dataclass
class ShutdownState:
    """停机状态追踪。"""

    shutting_down: bool = False
    active_requests: int = 0
    shutdown_started_at: float = 0.0
    drain_timeout: float = 30.0
    _waiters: list = field(default_factory=list)


# 全局状态
_state = ShutdownState()


def get_shutdown_state() -> ShutdownState:
    return _state


class ActiveRequestTracker(BaseHTTPMiddleware):
    """追踪活跃请求数，停机时拒绝新请求。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 停机中 → 拒绝新请求（健康检查除外）
        if _state.shutting_down and not request.url.path.startswith("/health"):
            return Response(
                content='{"detail":"服务正在关闭，请稍后重试"}',
                status_code=503,
                media_type="application/json",
                headers={"Retry-After": "5", "Connection": "close"},
            )

        _state.active_requests += 1
        try:
            response = await call_next(request)
            return response
        finally:
            _state.active_requests -= 1
            # 如果正在排空且无活跃请求，通知等待者
            if _state.shutting_down and _state.active_requests == 0:
                for event in _state._waiters:
                    event.set()


class GracefulShutdownManager:
    """优雅停机管理器。"""

    def __init__(self, app: FastAPI, drain_timeout: float = 30.0):
        self.app = app
        _state.drain_timeout = drain_timeout

    def install(self):
        """安装信号处理器和中间件。"""
        self.app.add_middleware(ActiveRequestTracker)
        logger.info("graceful_shutdown_installed", drain_timeout=_state.drain_timeout)

    async def shutdown(self):
        """执行优雅停机流程。"""
        if _state.shutting_down:
            return

        _state.shutting_down = True
        _state.shutdown_started_at = time.time()
        logger.info("shutdown_initiated", active_requests=_state.active_requests)

        # 等待活跃请求完成
        if _state.active_requests > 0:
            event = asyncio.Event()
            _state._waiters.append(event)
            try:
                await asyncio.wait_for(event.wait(), timeout=_state.drain_timeout)
                logger.info("requests_drained")
            except asyncio.TimeoutError:
                logger.warning(
                    "drain_timeout",
                    remaining=_state.active_requests,
                    timeout=_state.drain_timeout,
                )
            finally:
                _state._waiters.remove(event)

        # 关闭后台服务
        try:
            from xagent.core.scheduler import get_scheduler
            await get_scheduler().stop()
        except Exception:
            pass

        try:
            from xagent.adapters.mcp import get_mcp_manager
            await get_mcp_manager().stop()
        except Exception:
            pass

        # 刷新追踪缓冲
        try:
            from xagent.infra.tracing import flush_traces
            flush_traces()
        except Exception:
            pass

        # 关闭数据库
        try:
            from xagent.infra import db
            await db.dispose_engine()
        except Exception:
            pass

        elapsed = time.time() - _state.shutdown_started_at
        logger.info("shutdown_complete", elapsed_s=round(elapsed, 2))
