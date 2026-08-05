"""请求链路追踪：Trace ID 贯穿全链路。

每个请求分配唯一 X-Trace-ID：
- 客户端可传入（透传）
- 未传入则自动生成（UUID4 短格式）
- 注入到日志上下文（structlog bind）
- 响应头返回（便于排查）
- 下游调用透传（LLM / MCP / Webhook）

用法：
    app.add_middleware(TraceMiddleware)
    # 任意位置获取当前 trace_id:
    from xagent.api.trace import get_trace_id
    trace_id = get_trace_id()
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from xagent.infra.logging import get_logger

logger = get_logger("xagent.trace")

# 请求级 Trace ID 上下文变量
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

TRACE_HEADER = "X-Trace-ID"


def get_trace_id() -> str:
    """获取当前请求的 Trace ID。"""
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    """手动设置 Trace ID（用于后台任务等非 HTTP 上下文）。"""
    _trace_id_var.set(trace_id)


def generate_trace_id() -> str:
    """生成短格式 Trace ID（16 字符 hex）。"""
    return uuid.uuid4().hex[:16]


class TraceMiddleware(BaseHTTPMiddleware):
    """链路追踪中间件。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 提取或生成 Trace ID
        trace_id = request.headers.get(TRACE_HEADER.lower(), "") or generate_trace_id()

        # 设置上下文
        token = _trace_id_var.set(trace_id)

        try:
            # 绑定到 structlog 上下文
            import structlog
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(trace_id=trace_id)

            # 执行请求
            response = await call_next(request)

            # 响应头注入
            response.headers[TRACE_HEADER] = trace_id
            return response
        finally:
            _trace_id_var.reset(token)
