"""Langfuse / OpenTelemetry 追踪集成。

提供轻量 wrapper：
- 若安装 langfuse 且配置了 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY，则上报 trace
- 否则降级为本地 structured log（零依赖）

用法：
    from xagent.infra.tracing import trace_llm_call, trace_agent_run

    with trace_agent_run(goal="...", tenant_id="...") as span:
        result = await run_agent(...)
        span.set_output(result)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

from xagent.infra.logging import get_logger
from xagent.infra.settings import get_settings

logger = get_logger("xagent.tracing")

# ─── Langfuse 初始化（懒加载） ───
_langfuse_client: Any = None
_langfuse_tried = False


def _get_langfuse():
    global _langfuse_client, _langfuse_tried
    if _langfuse_tried:
        return _langfuse_client
    _langfuse_tried = True
    try:
        from langfuse import Langfuse
        s = get_settings()
        pk = getattr(s, "langfuse_public_key", "") or ""
        sk = getattr(s, "langfuse_secret_key", "") or ""
        host = getattr(s, "langfuse_host", "https://cloud.langfuse.com") or "https://cloud.langfuse.com"
        if pk and sk:
            _langfuse_client = Langfuse(public_key=pk, secret_key=sk, host=host)
            logger.info("langfuse_init", host=host)
        else:
            logger.debug("langfuse_skip", reason="no keys configured")
    except ImportError:
        logger.debug("langfuse_skip", reason="package not installed")
    return _langfuse_client


# ─── Span 抽象 ───
@dataclass
class TraceSpan:
    """轻量 span 抽象，兼容 Langfuse 和本地日志。"""
    name: str
    trace_id: str = ""
    start_time: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    _output: Any = None
    _lf_span: Any = None

    def set_output(self, output: Any) -> None:
        self._output = output
        if self._lf_span:
            try:
                self._lf_span.end(output=str(output)[:2000])
            except Exception:
                pass

    def set_error(self, error: str) -> None:
        if self._lf_span:
            try:
                self._lf_span.end(level="ERROR", status_message=error)
            except Exception:
                pass

    def end(self) -> None:
        duration_ms = (time.time() - self.start_time) * 1000
        if self._lf_span:
            try:
                self._lf_span.end()
            except Exception:
                pass
        else:
            logger.debug(
                "span_end",
                name=self.name,
                trace_id=self.trace_id,
                duration_ms=round(duration_ms, 1),
            )


# ─── 公开 API ───
@contextmanager
def trace_agent_run(
    goal: str,
    tenant_id: str = "",
    user_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> Generator[TraceSpan, None, None]:
    """追踪一次 Agent 运行。"""
    lf = _get_langfuse()
    span = TraceSpan(name="agent_run", metadata=metadata or {})

    if lf:
        try:
            trace = lf.trace(
                name="agent_run",
                user_id=user_id or None,
                metadata={"tenant_id": tenant_id, "goal": goal[:200], **(metadata or {})},
            )
            span.trace_id = trace.id if hasattr(trace, "id") else ""
            span._lf_span = trace.span(name="orchestration", input=goal[:500])
        except Exception:
            pass

    logger.info("trace_start", name="agent_run", goal=goal[:100], tenant_id=tenant_id)
    try:
        yield span
    except Exception as exc:
        span.set_error(str(exc))
        raise
    finally:
        span.end()


@contextmanager
def trace_llm_call(
    model: str,
    prompt_preview: str = "",
    metadata: dict[str, Any] | None = None,
) -> Generator[TraceSpan, None, None]:
    """追踪一次 LLM 调用。"""
    lf = _get_langfuse()
    span = TraceSpan(name="llm_call", metadata={"model": model, **(metadata or {})})

    if lf:
        try:
            span._lf_span = lf.generation(
                name=f"llm:{model}",
                model=model,
                input=prompt_preview[:1000],
            )
        except Exception:
            pass

    try:
        yield span
    except Exception as exc:
        span.set_error(str(exc))
        raise
    finally:
        span.end()


def flush_traces() -> None:
    """优雅关闭时刷新缓冲的 trace。"""
    lf = _get_langfuse()
    if lf:
        try:
            lf.flush()
        except Exception:
            pass
