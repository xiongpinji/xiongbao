"""追踪器工厂：配置了 Langfuse key 则用 LangfuseTracer，否则 NoopTracer。"""

from __future__ import annotations

from functools import lru_cache

from xagent.adapters.observability.base import NoopTracer, Tracer
from xagent.infra.settings import get_settings


@lru_cache
def get_tracer() -> Tracer:
    cfg = get_settings().observability
    if cfg.langfuse_host and cfg.langfuse_public_key and cfg.langfuse_secret_key:
        from xagent.adapters.observability.langfuse_tracer import LangfuseTracer

        return LangfuseTracer(cfg)
    return NoopTracer()


def reset_tracer() -> None:
    get_tracer.cache_clear()
