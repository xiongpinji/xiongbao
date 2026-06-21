"""Celery worker 集成（full/enterprise 模式）。

进程内 TaskRunner 为 lite 默认；配置 Redis broker 后，submit 可走 Celery
实现多实例横向扩展。两者接口一致（submit -> task_id -> poll）。

用法：
  celery -A xagent.worker.celery_app worker --loglevel=info
"""

from __future__ import annotations

from typing import Any

from xagent.infra.logging import get_logger
from xagent.infra.settings import get_settings

logger = get_logger("xagent.celery")

_celery_app = None


def get_celery_app():
    """惰性创建 Celery app（未配置 broker 返回 None）。"""
    global _celery_app
    if _celery_app is not None:
        return _celery_app
    settings = get_settings()
    broker = settings.cache.redis_url
    if not broker:
        return None
    try:
        from celery import Celery

        _celery_app = Celery("xagent", broker=broker, backend=broker)
        _celery_app.conf.update(
            task_serializer="json",
            result_serializer="json",
            accept_content=["json"],
            task_track_started=True,
            task_time_limit=600,
            task_soft_time_limit=540,
        )
        _celery_app.task(name="xagent.run_agent")(run_agent_task)
        logger.info("celery_initialized", broker=broker)
    except ImportError:
        logger.info("celery_not_installed", detail="未安装 celery，后台任务走进程内")
        return None
    return _celery_app


def run_agent_task(
    goal: str,
    role: str | None,
    capabilities: list[str],
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Celery 任务入口：同步包装异步 run_agent。"""
    import asyncio

    from xagent.core.orchestration import run_agent
    from xagent.enterprise.auth.principal import Principal

    principal = Principal(
        user_id=user_id, tenant_id=tenant_id, roles=frozenset({"member"})
    )
    result = asyncio.run(
        run_agent(
            goal,
            principal=principal,
            role_name=role,
            capabilities=set(capabilities) or None,
        )
    )
    return result.to_dict()


# 模块级 app（celery CLI -A 需要）
app = get_celery_app()
