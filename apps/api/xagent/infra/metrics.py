"""Prometheus 指标 + 请求计量中间件。

暴露 /metrics 端点（供 Prometheus scrape），记录：
- 请求计数（method, path, status）
- 请求延迟直方图
- 活跃连接数
- LLM 调用计数 + token 用量
- Agent 任务计数（status）
"""

from __future__ import annotations

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    _HAS_PROM = True
except ImportError:
    _HAS_PROM = False

from xagent.infra.logging import get_logger

logger = get_logger("xagent.metrics")

# ─── 指标定义 ───
if _HAS_PROM:
    REGISTRY = CollectorRegistry()

    REQUEST_COUNT = Counter(
        "xagent_http_requests_total",
        "HTTP 请求总数",
        ["method", "path", "status"],
        registry=REGISTRY,
    )
    REQUEST_LATENCY = Histogram(
        "xagent_http_request_duration_seconds",
        "HTTP 请求延迟",
        ["method", "path"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
        registry=REGISTRY,
    )
    ACTIVE_CONNECTIONS = Gauge(
        "xagent_active_connections",
        "当前活跃连接数",
        registry=REGISTRY,
    )
    LLM_CALLS = Counter(
        "xagent_llm_calls_total",
        "LLM 调用次数",
        ["model", "status"],
        registry=REGISTRY,
    )
    LLM_TOKENS = Counter(
        "xagent_llm_tokens_total",
        "LLM token 消耗",
        ["model", "kind"],  # kind: prompt / completion
        registry=REGISTRY,
    )
    AGENT_TASKS = Counter(
        "xagent_agent_tasks_total",
        "Agent 任务计数",
        ["status"],
        registry=REGISTRY,
    )
    MCP_TOOL_CALLS = Counter(
        "xagent_mcp_tool_calls_total",
        "MCP 工具调用次数",
        ["server", "tool", "status"],
        registry=REGISTRY,
    )


# ─── 中间件 ───
class MetricsMiddleware(BaseHTTPMiddleware):
    """请求计量中间件。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not _HAS_PROM:
            return await call_next(request)

        # 跳过 metrics 端点自身
        if request.url.path == "/metrics":
            return await call_next(request)

        try:
            ACTIVE_CONNECTIONS.inc()
        except Exception:  # noqa: S110
            pass
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception:
            status_code = "500"
            raise
        finally:
            duration = time.perf_counter() - start
            try:
                path = _normalize_path(request.url.path)
                REQUEST_COUNT.labels(method=request.method, path=path, status=status_code).inc()
                REQUEST_LATENCY.labels(method=request.method, path=path).observe(duration)
                ACTIVE_CONNECTIONS.dec()
            except Exception:  # noqa: S110
                pass

        return response


def _normalize_path(path: str) -> str:
    """将动态路径段归一化，防止指标基数爆炸。"""
    parts = path.strip("/").split("/")
    normalized = []
    for part in parts:
        # 看起来像 ID（hex/uuid/长数字）的段替换为 :id
        if len(part) > 16 or (part and part[0].isdigit() and len(part) > 4):
            normalized.append(":id")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized)


# ─── 便捷记录函数 ───
def record_llm_call(
    model: str, success: bool, prompt_tokens: int = 0, completion_tokens: int = 0,
) -> None:
    if not _HAS_PROM:
        return
    LLM_CALLS.labels(model=model, status="ok" if success else "error").inc()
    if prompt_tokens:
        LLM_TOKENS.labels(model=model, kind="prompt").inc(prompt_tokens)
    if completion_tokens:
        LLM_TOKENS.labels(model=model, kind="completion").inc(completion_tokens)


def record_agent_task(status: str) -> None:
    if not _HAS_PROM:
        return
    AGENT_TASKS.labels(status=status).inc()


def record_mcp_call(server: str, tool: str, success: bool) -> None:
    if not _HAS_PROM:
        return
    MCP_TOOL_CALLS.labels(server=server, tool=tool, status="ok" if success else "error").inc()


# ─── /metrics 端点 ───
def metrics_response() -> Response:
    """生成 Prometheus 格式指标响应。"""
    if not _HAS_PROM:
        return Response(content="# prometheus_client not installed\n", media_type="text/plain")
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
