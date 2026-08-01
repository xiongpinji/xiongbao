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
    # 从 SQLite 恢复持久化数据（Webhook/知识库）
    try:
        from xagent.core.knowledge import Document, get_knowledge_base
        from xagent.core.persistence import load_documents, load_webhooks
        from xagent.core.webhooks import WebhookConfig, get_webhook_manager
        hooks = await load_webhooks("default")
        wm = get_webhook_manager()
        for h in hooks:
            wm._hooks[h["webhook_id"]] = WebhookConfig(
                webhook_id=h["webhook_id"], tenant_id=h["tenant_id"],
                url=h["url"], events=h["events"], secret=h["secret"],
            )
        docs = await load_documents("default")
        kb = get_knowledge_base()
        for d in docs:
            kb._docs[d["doc_id"]] = Document(
                doc_id=d["doc_id"], title=d["title"],
                tenant_id=d["tenant_id"], source=d["source"],
                chunk_count=d["chunk_count"], tags=d["tags"],
            )
        logger.info("persistence_loaded", webhooks=len(hooks), docs=len(docs))
    except Exception:  # noqa: S110
        pass
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

    # 全局异常处理：防止未捕获异常导致连接中断
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(Exception)
    async def _global_exc_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        logger.error("unhandled_exception", path=request.url.path, error=str(exc))
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)

    # CORS（生产禁止通配符，已在 settings.validate_for_production 校验）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=300, window_seconds=60)
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

    # 性能统计端点
    @app.get("/perf", include_in_schema=False)
    async def _perf() -> dict:
        from xagent.infra.performance import get_api_cache, get_search_cache
        # 从中间件栈获取 timing 实例
        for m in app.user_middleware:
            if hasattr(m, "cls") and m.cls.__name__ == "TimingMiddleware":
                break
        return {
            "cache_api": get_api_cache().stats,
            "cache_search": get_search_cache().stats,
        }

    return app


# 供 uvicorn 直接引用：uvicorn xagent.main:app
app = create_app()
