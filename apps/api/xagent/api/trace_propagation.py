"""链路追踪传播：W3C Trace Context 中间件。

功能：
- 解析/生成 traceparent 头（W3C Trace Context）
- 注入 trace_id / span_id 到请求上下文
- 下游请求自动传播追踪头
- 响应头回传 trace_id（便于调试）

用法：
    from xagent.api.trace_propagation import TraceMiddleware, get_trace_context

    app.add_middleware(TraceMiddleware)
    # 在业务代码中：
    ctx = get_trace_context()
    headers = ctx.propagation_headers()  # 传给下游
"""

from __future__ import annotations

import os
import random
import string
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.trace")

# 请求级追踪上下文
_trace_context_var: ContextVar["TraceContext | None"] = ContextVar(
    "trace_context", default=None
)


def _random_hex(length: int) -> str:
    """生成随机十六进制字符串。"""
    return "".join(random.choices("0123456789abcdef", k=length))


@dataclass
class TraceContext:
    """W3C Trace Context。"""

    trace_id: str  # 32 hex chars
    span_id: str  # 16 hex chars
    parent_span_id: str | None = None
    trace_flags: str = "01"  # 01 = sampled
    version: str = "00"

    @property
    def traceparent(self) -> str:
        """生成 traceparent 头值。"""
        return f"{self.version}-{self.trace_id}-{self.span_id}-{self.trace_flags}"

    def propagation_headers(self) -> dict[str, str]:
        """生成传播到下游的请求头。"""
        return {
            "traceparent": self.traceparent,
            "X-Trace-Id": self.trace_id,
        }

    @classmethod
    def from_traceparent(cls, header: str) -> "TraceContext | None":
        """解析 traceparent 头。"""
        parts = header.strip().split("-")
        if len(parts) < 4:
            return None
        version, trace_id, parent_span_id, flags = parts[0], parts[1], parts[2], parts[3]
        if len(trace_id) != 32 or len(parent_span_id) != 16:
            return None
        return cls(
            trace_id=trace_id,
            span_id=_random_hex(16),  # 新 span
            parent_span_id=parent_span_id,
            trace_flags=flags,
            version=version,
        )

    @classmethod
    def new(cls) -> "TraceContext":
        """创建全新追踪上下文。"""
        return cls(
            trace_id=_random_hex(32),
            span_id=_random_hex(16),
        )


def get_trace_context() -> TraceContext | None:
    """获取当前请求的追踪上下文。"""
    return _trace_context_var.get()


class TraceMiddleware(BaseHTTPMiddleware):
    """W3C Trace Context 传播中间件。"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 解析或创建追踪上下文
        traceparent = request.headers.get("traceparent", "")
        ctx = TraceContext.from_traceparent(traceparent) if traceparent else None
        if not ctx:
            ctx = TraceContext.new()

        # 设置上下文变量
        token = _trace_context_var.set(ctx)

        try:
            response = await call_next(request)
            # 响应头回传 trace_id
            response.headers["X-Trace-Id"] = ctx.trace_id
            response.headers["traceparent"] = ctx.traceparent
            return response
        finally:
            _trace_context_var.reset(token)
