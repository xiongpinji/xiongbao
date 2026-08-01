"""健康检查聚合：多依赖健康状态统一上报。

功能：
- 注册多个依赖健康检查
- 并行执行检查
- 降级策略（部分失败不阻塞）
- 缓存结果减少开销

用法：
    from xagent.api.health_aggregator import HealthAggregator

    health = HealthAggregator()
    health.register("database", check_db, timeout_s=3)
    health.register("redis", check_redis, timeout_s=2)

    status = await health.check_all()
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.health")


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """组件健康结果。"""

    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str = ""
    checked_at: float = field(default_factory=time.time)


@dataclass
class HealthCheckEntry:
    """注册的健康检查。"""

    name: str
    fn: Callable[[], Coroutine[Any, Any, bool]]
    timeout_s: float = 5.0
    critical: bool = True  # 关键组件失败 → unhealthy
    cache_ttl_s: float = 10.0
    last_result: ComponentHealth | None = None
    last_check_time: float = 0.0


class HealthAggregator:
    """健康检查聚合器。"""

    def __init__(self, cache_ttl_s: float = 10.0):
        self._checks: dict[str, HealthCheckEntry] = {}
        self._cache_ttl_s = cache_ttl_s

    def register(
        self,
        name: str,
        fn: Callable[[], Coroutine[Any, Any, bool]],
        timeout_s: float = 5.0,
        critical: bool = True,
        cache_ttl_s: float | None = None,
    ) -> None:
        """注册健康检查。"""
        self._checks[name] = HealthCheckEntry(
            name=name,
            fn=fn,
            timeout_s=timeout_s,
            critical=critical,
            cache_ttl_s=cache_ttl_s or self._cache_ttl_s,
        )
        logger.info("health check registered: %s (critical=%s)", name, critical)

    def unregister(self, name: str) -> None:
        """注销。"""
        self._checks.pop(name, None)

    async def check_all(self, force: bool = False) -> dict[str, Any]:
        """执行所有健康检查。"""
        now = time.time()
        tasks = []

        for entry in self._checks.values():
            # 缓存未过期则跳过
            if not force and entry.last_result and (now - entry.last_check_time) < entry.cache_ttl_s:
                continue
            tasks.append(self._check_one(entry))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # 汇总
        results = []
        overall = HealthStatus.HEALTHY

        for entry in self._checks.values():
            result = entry.last_result
            if result is None:
                result = ComponentHealth(name=entry.name, status=HealthStatus.UNHEALTHY, message="never checked")
            results.append({
                "name": result.name,
                "status": result.status.value,
                "latency_ms": round(result.latency_ms, 1),
                "message": result.message,
            })
            if result.status == HealthStatus.UNHEALTHY and entry.critical:
                overall = HealthStatus.UNHEALTHY
            elif result.status != HealthStatus.HEALTHY and overall == HealthStatus.HEALTHY:
                overall = HealthStatus.DEGRADED

        return {
            "status": overall.value,
            "components": results,
            "checked_at": time.time(),
        }

    async def _check_one(self, entry: HealthCheckEntry) -> None:
        """执行单个检查。"""
        start = time.time()
        try:
            result = await asyncio.wait_for(entry.fn(), timeout=entry.timeout_s)
            latency = (time.time() - start) * 1000
            status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
            entry.last_result = ComponentHealth(
                name=entry.name,
                status=status,
                latency_ms=latency,
                message="ok" if result else "check returned false",
            )
        except asyncio.TimeoutError:
            latency = (time.time() - start) * 1000
            entry.last_result = ComponentHealth(
                name=entry.name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"timeout after {entry.timeout_s}s",
            )
        except Exception as exc:
            latency = (time.time() - start) * 1000
            entry.last_result = ComponentHealth(
                name=entry.name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=str(exc)[:200],
            )

        entry.last_check_time = time.time()

    async def check_single(self, name: str) -> ComponentHealth | None:
        """检查单个组件。"""
        entry = self._checks.get(name)
        if not entry:
            return None
        await self._check_one(entry)
        return entry.last_result


# 全局实例
health_aggregator = HealthAggregator()
