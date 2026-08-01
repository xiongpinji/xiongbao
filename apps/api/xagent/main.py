"""FastAPI 应用装配。

设计：
- ``create_app()`` 工厂，便于测试构造多实例。
- lifespan 管理启动/关闭（生产配置校验、可观测初始化、资源释放）。
- 中间件顺序：CORS → 请求上下文/日志。
- 路由按域挂载（Phase 0 仅 system；后续 phase 追加）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from xagent import __version__
from xagent.adapters.mcp import get_mcp_manager
from xagent.api import system
from xagent.api.middleware import RequestContextMiddleware
from xagent.api.security_middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from xagent.api.v1 import api_v1
from xagent.infra import db
from xagent.infra.logging import configure_logging, get_logger
from xagent.infra.metrics import MetricsMiddleware, metrics_response
from xagent.infra.settings import get_settings

logger = get_logger("xagent.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(debug=settings.debug)

    # 生产配置硬校验：有问题直接拒绝启动
    problems = settings.validate_for_production()
    if problems:
        for p in problems:
            logger.error("config_invalid", problem=p)
        raise RuntimeError(f"生产配置校验失败: {problems}")

    logger.info(
        "startup",
        app=settings.app_name,
        version=__version__,
        mode=settings.mode.value,
    )
    # 自动建表（SQLite 开发模式，生产用 alembic）
    import xagent.infra.models  # noqa: F401  确保所有 ORM 模型注册
    async with db.get_engine().begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    # 启动 MCP 管理器（无 server 时安全空转）
    await get_mcp_manager().start()
    # 启动定时调度器
    from xagent.core.scheduler import get_scheduler
    await get_scheduler().start()
    yield
    # ---- shutdown ----
    await get_scheduler().stop()
    await get_mcp_manager().stop()
    # 刷新追踪缓冲
    from xagent.infra.tracing import flush_traces
    flush_traces()
    await db.dispose_engine()
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="X-Agent — 面向企业的自主智能体框架（开源重构版）",
        lifespan=lifespan,
    )

    # CORS（生产禁止通配符，已在 settings.validate_for_production 校验）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # 路由挂载
    app.include_router(system.router)
    app.include_router(api_v1)

    # Prometheus 指标端点
    from fastapi import Response
    @app.get("/metrics", include_in_schema=False)
    async def _metrics() -> Response:
        return metrics_response()

    return app


# 供 uvicorn 直接引用：uvicorn xagent.main:app
app = create_app()
