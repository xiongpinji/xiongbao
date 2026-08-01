"""请求关联ID：跨服务请求追踪。

功能：
- 生成/传播 X-Correlation-Id
- 跨异步任务关联
- 日志自动注入 correlation_id
- 响应头回传

用法：
    from xagent.api.request_correlation import CorrelationMiddleware, get_correlation_id

    app.add_middleware(CorrelationMiddleware)
    # 在业务代码中：
    cid = get_correlation_id()  # 当前请求的关联ID
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.correlation")

# 请求级关联ID
_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

HEADER_NAME = "X-Correlation-Id"


def get_correlation_id() -> str:
    """获取当前请求的关联ID。"""
    return _correlation_id_var.get()


def set_correlation_id(cid: str) -> None:
    """手动设置关联ID（用于后台任务）。"""
    _correlation_id_var.set(cid)


def new_correlation_id() -> str:
    """生成新的关联ID。"""
    cid = uuid.uuid4().hex[:16]
    _correlation_id_var.set(cid)
    return cid


class CorrelationMiddleware(BaseHTTPMiddleware):
    """关联ID中间件。"""

    def __init__(self, app, header_name: str = HEADER_NAME):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 从请求头获取或生成
        cid = request.headers.get(self.header_name, "")
        if not cid:
            cid = uuid.uuid4().hex[:16]

        # 设置上下文
        token = _correlation_id_var.set(cid)

        try:
            response = await call_next(request)
            # 响应头回传
            response.headers[self.header_name] = cid
            return response
        finally:
            _correlation_id_var.reset(token)


class CorrelationFilter:
    """日志过滤器：自动注入 correlation_id。"""

    def filter(self, record) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True


# 便捷函数：为后台任务创建关联上下文
def task_correlation(task_name: str = "") -> str:
    """为异步任务创建新的关联ID。"""
    cid = new_correlation_id()
    logger.info("task correlation started: %s [%s]", task_name or "unnamed", cid)
    return cid
