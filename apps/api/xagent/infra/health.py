"""健康探针：liveness 与 readiness。

- ``/health``（liveness）：进程存活即 200，不查依赖。
- ``/ready``（readiness）：检查关键依赖（DB / 缓存），任一不可用则 503。
  采用「降级感知」：lite 模式下内存缓存恒可用，外部依赖缺失不算失败。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from xagent.infra import db
from xagent.infra.cache import get_cache


@dataclass
class ComponentHealth:
    name: str
    healthy: bool
    detail: str = ""


@dataclass
class ReadinessReport:
    ready: bool
    components: list[ComponentHealth] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "components": [
                {"name": c.name, "healthy": c.healthy, "detail": c.detail}
                for c in self.components
            ],
        }


async def check_readiness() -> ReadinessReport:
    """聚合关键依赖健康状态。"""
    components: list[ComponentHealth] = []

    db_ok = await db.ping()
    components.append(
        ComponentHealth("database", db_ok, "" if db_ok else "数据库不可达")
    )

    try:
        cache_ok = await get_cache().ping()
    except Exception as exc:  # pragma: no cover - defensive
        cache_ok = False
        cache_detail = str(exc)
    else:
        cache_detail = "" if cache_ok else "缓存不可达"
    components.append(ComponentHealth("cache", cache_ok, cache_detail))

    ready = all(c.healthy for c in components)
    return ReadinessReport(ready=ready, components=components)
