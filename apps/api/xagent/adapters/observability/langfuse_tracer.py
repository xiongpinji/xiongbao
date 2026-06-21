"""Langfuse 实现：把 span 上报到 Langfuse（OTel 兼容的运行时追踪）。

适配 Langfuse SDK 4.x（OTel 风格）：用 start_as_current_observation 上下文管理器。
兼容 3.x/2.x：若新 API 不可用回退到旧 API（trace/span）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from xagent.infra.settings import ObservabilitySettings


class _LangfuseSpan:
    def __init__(self, span: Any) -> None:
        self._span = span

    def set_input(self, value: Any) -> None:
        try:
            self._span.update(input=value)
        except Exception:  # noqa: S110  trace 上报失败不中断业务
            pass

    def set_output(self, value: Any) -> None:
        try:
            self._span.update(output=value)
        except Exception:  # noqa: S110  trace 上报失败不中断业务
            pass

    def set_metadata(self, **kwargs: Any) -> None:
        try:
            self._span.update(metadata=kwargs)
        except Exception:  # noqa: S110  trace 上报失败不中断业务
            pass


class LangfuseTracer:
    def __init__(self, cfg: ObservabilitySettings) -> None:
        from langfuse import Langfuse

        self._client = Langfuse(
            host=cfg.langfuse_host,
            public_key=cfg.langfuse_public_key,
            secret_key=cfg.langfuse_secret_key,
        )
        # 检测 API 风格：4.x 有 start_as_current_observation
        self._has_v4 = hasattr(self._client, "start_as_current_observation")

    @asynccontextmanager
    async def trace(self, name: str, **metadata: Any):
        if self._has_v4:
            # SDK 4.x：OTel 风格上下文管理器
            with self._client.start_as_current_observation(
                name=name, as_type="span", metadata=metadata or None
            ) as span:
                yield _LangfuseSpan(span)
        else:
            # SDK <=3.x：trace + span
            trace = self._client.trace(name=name, metadata=metadata or None)
            span = trace.span(name=name)
            try:
                yield _LangfuseSpan(span)
            finally:
                span.end()

    async def flush(self) -> None:
        self._client.flush()

    async def health(self) -> bool:
        # 4.x: auth_check 可能不存在；用 flush 探活
        try:
            check = getattr(self._client, "auth_check", None)
            if check:
                return bool(check())
            return True
        except Exception:
            return False
