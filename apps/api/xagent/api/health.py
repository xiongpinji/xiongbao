"""增强健康检查：依赖服务探活 + 降级状态。

端点：
- GET /health/live   → 存活探针（进程活着即 200）
- GET /health/ready  → 就绪探针（核心依赖可用）
- GET /health/deep   → 深度检查（所有依赖 + 延迟）

降级策略：
- 数据库不可用 → 只读模式
- Redis 不可用 → 跳过缓存
- Qdrant 不可用 → 禁用向量搜索
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from xagent.infra.logging import get_logger
from xagent.infra.settings import get_settings

router = APIRouter(prefix="/health", tags=["system"])
logger = get_logger("xagent.health")


async def _check_db() -> dict:
    """检查数据库连接。"""
    try:
        from xagent.infra import db
        async with db.get_engine().connect() as conn:
            await conn.execute(db.text("SELECT 1"))
        return {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:200]}


async def _check_redis() -> dict:
    """检查 Redis 连接。"""
    settings = get_settings()
    redis_url = getattr(settings.cache, "redis_url", None) if hasattr(settings, "cache") else None
    if not redis_url:
        return {"status": "skipped", "reason": "not_configured"}
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(redis_url, socket_connect_timeout=3)
        start = time.perf_counter()
        await r.ping()
        latency = (time.perf_counter() - start) * 1000
        await r.aclose()
        return {"status": "healthy", "latency_ms": round(latency, 1)}
    except Exception as e:
        return {"status": "degraded", "error": str(e)[:200], "fallback": "skip_cache"}


async def _check_qdrant() -> dict:
    """检查 Qdrant 向量数据库。"""
    settings = get_settings()
    qdrant_url = getattr(settings.memory, "qdrant_url", None) if hasattr(settings, "memory") else None
    if not qdrant_url:
        return {"status": "skipped", "reason": "not_configured"}
    try:
        import httpx
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{qdrant_url}/healthz")
        latency = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            return {"status": "healthy", "latency_ms": round(latency, 1)}
        return {"status": "degraded", "error": f"HTTP {resp.status_code}", "fallback": "disable_vector_search"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)[:200], "fallback": "disable_vector_search"}


@router.get("/live", summary="存活探针")
async def liveness():
    """Kubernetes liveness：进程活着即返回 200。"""
    return {"status": "alive", "timestamp": time.time()}


@router.get("/ready", summary="就绪探针")
async def readiness():
    """Kubernetes readiness：数据库可用即就绪。"""
    db_check = await _check_db()
    if db_check["status"] == "healthy":
        return {"status": "ready", "checks": {"database": db_check}}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "checks": {"database": db_check}},
    )


@router.get("/deep", summary="深度健康检查")
async def deep_health():
    """深度检查所有依赖服务，返回降级建议。"""
    checks = await asyncio.gather(
        _check_db(),
        _check_redis(),
        _check_qdrant(),
        return_exceptions=True,
    )

    results = {
        "database": checks[0] if not isinstance(checks[0], Exception) else {"status": "error", "error": str(checks[0])[:200]},
        "redis": checks[1] if not isinstance(checks[1], Exception) else {"status": "error", "error": str(checks[1])[:200]},
        "qdrant": checks[2] if not isinstance(checks[2], Exception) else {"status": "error", "error": str(checks[2])[:200]},
    }

    # 降级模式判定
    degraded_services = [k for k, v in results.items() if v.get("status") in ("degraded", "unhealthy", "error")]
    overall = "healthy" if not degraded_services else ("degraded" if results["database"]["status"] == "healthy" else "unhealthy")

    status_code = 200 if overall != "unhealthy" else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "degraded_services": degraded_services,
            "checks": results,
            "timestamp": time.time(),
        },
    )
