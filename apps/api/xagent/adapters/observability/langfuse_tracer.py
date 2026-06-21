"""Langfuse 实现：把 span 上报到 Langfuse（OTel 兼容的运行时追踪）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from xagent.infra.settings import ObservabilitySettings


class _LangfuseSpan:
    def __init__(self, span: Any) -> None:
        self._span = span

    def set_input(self, value: Any) -> None:
        self._span.update(input=value)

    def set_output(self, value: Any) -> None:
        self._span.update(output=value)

    def set_metadata(self, **kwargs: Any) -> None:
        self._span.update(metadata=kwargs)


class LangfuseTracer:
    def __init__(self, cfg: ObservabilitySettings) -> None:
        from langfuse import Langfuse

        self._client = Langfuse(
            host=cfg.langfuse_host,
            public_key=cfg.langfuse_public_key,
            secret_key=cfg.langfuse_secret_key,
        )

    @asynccontextmanager
    async def trace(self, name: str, **metadata: Any):
        trace = self._client.trace(name=name, metadata=metadata or None)
        span = trace.span(name=name)
        try:
            yield _LangfuseSpan(span)
        finally:
            span.end()

    async def flush(self) -> None:
        self._client.flush()

    async def health(self) -> bool:
        try:
            return bool(self._client.auth_check())
        except Exception:
            return False
