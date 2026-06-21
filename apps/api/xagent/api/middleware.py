"""中间件：请求 ID 注入 + 结构化访问日志 + 租户上下文占位。

Phase 0 实现基础的 request_id + 访问日志；租户隔离的强制校验在 Phase 1
接入鉴权后补全（这里先解析并绑定 tenant_id 上下文，便于日志关联）。
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import (
    bind_request_context,
    clear_request_context,
    get_logger,
)

logger = get_logger("xagent.http")

REQUEST_ID_HEADER = "x-request-id"
TENANT_HEADER = "x-tenant-id"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 request_id，记录访问日志，绑定日志上下文。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        tenant_id = request.headers.get(TENANT_HEADER, "")
        bind_request_context(request_id=request_id, tenant_id=tenant_id)

        # 暴露给下游 handler
        request.state.request_id = request_id
        request.state.tenant_id = tenant_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                elapsed_ms=round(elapsed_ms, 2),
            )
            clear_request_context()
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        # Prometheus 指标
        try:
            from xagent.adapters.observability.metrics import http_requests

            http_requests.labels(
                method=request.method,
                path=request.url.path,
                status=str(response.status_code),
            ).inc()
        except Exception:  # noqa: S110  指标失败不影响请求
            pass
        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=round(elapsed_ms, 2),
        )
        clear_request_context()
        return response
