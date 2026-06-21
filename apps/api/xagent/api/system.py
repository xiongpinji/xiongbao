"""系统级路由：健康探针 + 元信息。"""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from xagent import __version__
from xagent.adapters.observability.metrics import metrics_output
from xagent.infra.health import check_readiness
from xagent.infra.settings import get_settings

router = APIRouter(tags=["system"])


@router.get("/health", summary="存活探针 (liveness)")
async def health() -> dict:
    """进程存活即返回 200，不查依赖。"""
    return {"status": "ok", "version": __version__}


@router.get("/ready", summary="就绪探针 (readiness)")
async def ready(response: Response) -> dict:
    """检查关键依赖；任一不可用返回 503。"""
    report = await check_readiness()
    if not report.ready:
        response.status_code = 503
    return report.to_dict()


@router.get("/meta", summary="运行时元信息")
async def meta() -> dict:
    settings = get_settings()
    return {
        "name": settings.app_name,
        "version": __version__,
        "mode": settings.mode.value,
        "debug": settings.debug,
    }


@router.get("/metrics", summary="Prometheus 指标", response_class=PlainTextResponse)
async def metrics() -> str:
    return metrics_output().decode("utf-8")
