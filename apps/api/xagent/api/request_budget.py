"""请求预算：限制单次请求的资源消耗。

功能：
- 限制请求最大耗时
- 限制响应体最大大小
- 限制下游调用次数
- 预算耗尽时优雅降级

用法：
    from xagent.api.request_budget import BudgetMiddleware, get_budget

    app.add_middleware(BudgetMiddleware, max_duration_s=10, max_response_bytes=5*1024*1024)
    # 业务代码中：
    budget = get_budget()
    if budget.remaining_calls <= 0:
        return cached_result  # 降级
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.budget")


@dataclass
class RequestBudget:
    """请求预算。"""

    max_duration_s: float = 30.0
    max_response_bytes: int = 10 * 1024 * 1024  # 10MB
    max_downstream_calls: int = 50
    start_time: float = field(default_factory=time.time)
    downstream_calls: int = 0
    response_bytes: int = 0

    @property
    def elapsed_s(self) -> float:
        return time.time() - self.start_time

    @property
    def remaining_time_s(self) -> float:
        return max(0, self.max_duration_s - self.elapsed_s)

    @property
    def remaining_calls(self) -> int:
        return max(0, self.max_downstream_calls - self.downstream_calls)

    @property
    def is_time_exhausted(self) -> bool:
        return self.elapsed_s >= self.max_duration_s

    @property
    def is_calls_exhausted(self) -> bool:
        return self.downstream_calls >= self.max_downstream_calls

    def consume_call(self) -> bool:
        """消耗一次下游调用配额。返回是否允许。"""
        if self.is_calls_exhausted:
            return False
        self.downstream_calls += 1
        return True

    def consume_bytes(self, size: int) -> bool:
        """消耗响应字节配额。"""
        self.response_bytes += size
        return self.response_bytes <= self.max_response_bytes


# 请求级预算
_budget_var: ContextVar[RequestBudget | None] = ContextVar("request_budget", default=None)


def get_budget() -> RequestBudget:
    """获取当前请求预算。"""
    budget = _budget_var.get()
    if budget is None:
        budget = RequestBudget()
        _budget_var.set(budget)
    return budget


class BudgetMiddleware(BaseHTTPMiddleware):
    """请求预算中间件。"""

    def __init__(
        self,
        app,
        max_duration_s: float = 30.0,
        max_response_bytes: int = 10 * 1024 * 1024,
        max_downstream_calls: int = 50,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.max_duration_s = max_duration_s
        self.max_response_bytes = max_response_bytes
        self.max_downstream_calls = max_downstream_calls
        self.exclude_prefixes = exclude_prefixes or ["/health", "/ws"]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        # 创建预算
        budget = RequestBudget(
            max_duration_s=self.max_duration_s,
            max_response_bytes=self.max_response_bytes,
            max_downstream_calls=self.max_downstream_calls,
        )
        token = _budget_var.set(budget)

        try:
            response = await call_next(request)

            # 检查是否超时
            if budget.is_time_exhausted:
                logger.warning(
                    "budget time exhausted: %s %s (%.1fs)",
                    request.method, path, budget.elapsed_s,
                )
                response.headers["X-Budget-Warning"] = "time_exhausted"

            return response
        finally:
            _budget_var.reset(token)
