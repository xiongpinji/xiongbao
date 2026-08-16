"""中间件：请求 ID 注入 + 结构化访问日志 + 租户上下文占位。

Phase 0 实现基础的 request_id + 访问日志；租户隔离的强制校验在 Phase 1
接入鉴权后补全（这里先解析并绑定 tenant_id 上下文，便于日志关联）。
"""

from __future__ import annotations

import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from xagent.infra.logging import (
    bind_request_context,
    clear_request_context,
    get_logger,
)

logger = get_logger("xagent.http")

REQUEST_ID_HEADER = "x-request-id"
TENANT_HEADER = "x-tenant-id"


class RequestContextMiddleware:
    """为每个请求注入 request_id，记录访问日志，绑定日志上下文。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        tenant_id = headers.get(TENANT_HEADER, "")
        bind_request_context(request_id=request_id, tenant_id=tenant_id)

        # 暴露给下游 handler
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["tenant_id"] = tenant_id

        method = scope.get("method", "")
        path = scope.get("path", "")
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request_failed",
                method=method,
                path=path,
                elapsed_ms=round(elapsed_ms, 2),
            )
            raise
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000
            # Prometheus 指标
            try:
                from xagent.adapters.observability.metrics import http_requests

                http_requests.labels(
                    method=method,
                    path=path,
                    status=str(status_code),
                ).inc()
            except Exception:  # noqa: S110  指标失败不影响请求
                pass
            logger.debug(
                "request",
                method=method,
                path=path,
                status=status_code,
                elapsed_ms=round(elapsed_ms, 2),
                request_id=request_id,  # 显式携带：内层中间件可能清空 contextvars
            )
        finally:
            clear_request_context()
