"""存活/就绪探针：Kubernetes 健康检查。

功能：
- /healthz（Liveness）：进程是否存活
- /readyz（Readiness）：是否可接收流量
- 可注册就绪条件
- 启动延迟保护

用法：
    from xagent.api.liveness_probe import probe_router, readiness_gate

    # 注册就绪条件：
    readiness_gate("database", check_db_connection)
    readiness_gate("cache", check_redis)

    # 路由：
    app.include_router(probe_router)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from xagent.infra.logging import get_logger

logger = get_logger("xagent.probe")

# 启动时间
_start_time = time.time()


@dataclass
class ReadinessCheck:
    """就绪检查项。"""

    name: str
    fn: Callable[[], Coroutine[Any, Any, bool]]
    timeout: float = 5.0
    last_result: bool = False
    last_check: float = 0
    error: str = ""


class ProbeManager:
    """探针管理器。"""

    def __init__(self, startup_delay: float = 5.0):
        self.startup_delay = startup_delay
        self._checks: dict[str, ReadinessCheck] = {}
        self._started = False

    def register(
        self,
        name: str,
        fn: Callable[[], Coroutine[Any, Any, bool]],
        timeout: float = 5.0,
    ) -> None:
        """注册就绪检查。"""
        self._checks[name] = ReadinessCheck(name=name, fn=fn, timeout=timeout)

    def mark_started(self) -> None:
        """标记应用已启动。"""
        self._started = True
        logger.info("application marked as started")

    async def liveness(self) -> dict:
        """存活检查。"""
        uptime = time.time() - _start_time
        return {
            "status": "alive",
            "uptime_s": round(uptime, 1),
            "started": self._started,
        }

    async def readiness(self) -> tuple[dict, int]:
        """就绪检查。"""
        # 启动延迟期
        uptime = time.time() - _start_time
        if uptime < self.startup_delay:
            return {"status": "starting", "uptime_s": round(uptime, 1)}, 503

        if not self._started:
            return {"status": "not_started"}, 503

        # 执行所有检查
        results = {}
        all_ready = True

        for name, check in self._checks.items():
            try:
                result = await asyncio.wait_for(check.fn(), timeout=check.timeout)
                check.last_result = result
                check.error = ""
            except asyncio.TimeoutError:
                result = False
                check.error = "timeout"
            except Exception as exc:
                result = False
                check.error = str(exc)[:100]

            check.last_check = time.time()
            results[name] = {"ready": result, "error": check.error}

            if not result:
                all_ready = False

        status = "ready" if all_ready else "not_ready"
        code = 200 if all_ready else 503

        return {"status": status, "checks": results}, code


# 全局实例
probe_manager = ProbeManager()


# 便捷函数
def readiness_gate(name: str, fn: Callable[[], Coroutine[Any, Any, bool]], timeout: float = 5.0):
    """注册就绪条件。"""
    probe_manager.register(name, fn, timeout)


# Starlette 路由
async def healthz_endpoint(request: Request) -> JSONResponse:
    """Liveness 端点。"""
    data = await probe_manager.liveness()
    return JSONResponse(content=data, status_code=200)


async def readyz_endpoint(request: Request) -> JSONResponse:
    """Readiness 端点。"""
    data, code = await probe_manager.readiness()
    return JSONResponse(content=data, status_code=code)


probe_router = [
    Route("/healthz", healthz_endpoint, methods=["GET"]),
    Route("/readyz", readyz_endpoint, methods=["GET"]),
]
