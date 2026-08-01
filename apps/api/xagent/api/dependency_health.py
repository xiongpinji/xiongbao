"""依赖健康检查：外部服务可用性探测。

功能：
- 检查数据库 / Redis / LLM API 等外部依赖
- 超时控制 + 降级标记
- 聚合报告（/health/deep 使用）

用法：
    from xagent.api.dependency_health import health_checker, DependencyCheck

    health_checker.register("database", check_db)
    health_checker.register("redis", check_redis, timeout=3.0)
    report = await health_checker.check_all()
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.dep_health")


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class DependencyResult:
    """单个依赖检查结果。"""

    name: str
    status: HealthStatus
    latency_ms: float
    message: str = ""
    checked_at: float = field(default_factory=time.time)


@dataclass
class DependencyRegistration:
    """依赖注册项。"""

    name: str
    check_fn: Callable[[], Coroutine[Any, Any, bool]]
    timeout: float = 5.0
    critical: bool = True  # 关键依赖失败 → 整体 unhealthy


class DependencyHealthChecker:
    """依赖健康检查器。"""

    def __init__(self):
        self._dependencies: dict[str, DependencyRegistration] = {}
        self._last_results: dict[str, DependencyResult] = {}

    def register(
        self,
        name: str,
        check_fn: Callable[[], Coroutine[Any, Any, bool]],
        timeout: float = 5.0,
        critical: bool = True,
    ) -> None:
        """注册依赖检查。"""
        self._dependencies[name] = DependencyRegistration(
            name=name, check_fn=check_fn, timeout=timeout, critical=critical
        )

    async def check_one(self, name: str) -> DependencyResult:
        """检查单个依赖。"""
        dep = self._dependencies.get(name)
        if not dep:
            return DependencyResult(
                name=name, status=HealthStatus.UNKNOWN, latency_ms=0, message="not registered"
            )

        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(dep.check_fn(), timeout=dep.timeout)
            latency = (time.perf_counter() - start) * 1000
            status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
            msg = "" if result else "check returned False"
        except asyncio.TimeoutError:
            latency = dep.timeout * 1000
            status = HealthStatus.UNHEALTHY
            msg = f"timeout after {dep.timeout}s"
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            status = HealthStatus.UNHEALTHY
            msg = str(exc)[:200]

        result = DependencyResult(
            name=name, status=status, latency_ms=round(latency, 1), message=msg
        )
        self._last_results[name] = result
        return result

    async def check_all(self) -> dict[str, Any]:
        """检查所有依赖，返回聚合报告。"""
        tasks = [self.check_one(name) for name in self._dependencies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        dependencies = {}
        overall = HealthStatus.HEALTHY

        for r in results:
            if isinstance(r, Exception):
                continue
            dependencies[r.name] = {
                "status": r.status.value,
                "latency_ms": r.latency_ms,
                "message": r.message,
            }
            dep = self._dependencies.get(r.name)
            if r.status == HealthStatus.UNHEALTHY:
                if dep and dep.critical:
                    overall = HealthStatus.UNHEALTHY
                elif overall == HealthStatus.HEALTHY:
                    overall = HealthStatus.DEGRADED

        return {
            "status": overall.value,
            "dependencies": dependencies,
            "checked_at": time.time(),
        }

    @property
    def last_results(self) -> dict[str, DependencyResult]:
        return self._last_results


# 全局单例
health_checker = DependencyHealthChecker()
