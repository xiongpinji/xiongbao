"""请求日志：结构化访问日志。

功能：
- 请求/响应结构化记录
- 耗时统计
- 敏感字段脱敏
- 慢请求告警

用法：
    from xagent.api.request_logging import RequestLoggingMiddleware

    app.add_middleware(RequestLoggingMiddleware, slow_threshold_ms=1000)
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.access")

SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件。"""

    def __init__(
        self,
        app,
        slow_threshold_ms: float = 1000.0,
        exclude_prefixes: list[str] | None = None,
        log_headers: bool = False,
    ):
        super().__init__(app)
        self.slow_threshold_ms = slow_threshold_ms
        self.exclude_prefixes = exclude_prefixes or ["/health", "/ws", "/static"]
        self.log_headers = log_headers

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:8])
        start = time.time()
        method = request.method
        client = request.client.host if request.client else "-"

        try:
            response = await call_next(request)
            elapsed_ms = (time.time() - start) * 1000
            status = response.status_code

            # 结构化日志
            log_data = {
                "request_id": request_id,
                "method": method,
                "path": path,
                "status": status,
                "elapsed_ms": round(elapsed_ms, 1),
                "client": client,
            }

            if self.log_headers:
                log_data["headers"] = {
                    k: ("***" if k.lower() in SENSITIVE_HEADERS else v)
                    for k, v in request.headers.items()
                }

            if elapsed_ms >= self.slow_threshold_ms:
                logger.warning("slow_request %s", log_data)
            elif status >= 500:
                logger.error("server_error %s", log_data)
            elif status >= 400:
                logger.info("client_error %s", log_data)
            else:
                logger.info("request %s", log_data)

            response.headers["X-Request-Id"] = request_id
            return response

        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            logger.error(
                "request_exception request_id=%s method=%s path=%s elapsed=%.1fms error=%s",
                request_id, method, path, elapsed_ms, exc,
            )
            raise
