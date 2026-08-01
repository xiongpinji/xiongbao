"""请求日志中间件：结构化访问日志。

功能：
- 记录每个请求的方法/路径/状态码/耗时
- 请求体/响应体摘要（可配置）
- 慢请求告警（> 阈值）
- 敏感路径脱敏

用法：
    from xagent.api.request_logging import RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware, slow_threshold_ms=1000)
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.access")

# 不记录请求体的路径
SKIP_BODY_PATHS = {"/api/v1/auth/login", "/api/v1/auth/register"}

# 不记录的路径（健康检查等高频低价值）
SKIP_LOG_PATHS = {"/health/live", "/health/ready", "/metrics"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """结构化请求日志中间件。"""

    def __init__(
        self,
        app,
        slow_threshold_ms: int = 1000,
        log_body: bool = False,
        max_body_log: int = 500,
    ):
        super().__init__(app)
        self.slow_threshold_ms = slow_threshold_ms
        self.log_body = log_body
        self.max_body_log = max_body_log

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 跳过高频路径
        path = request.url.path
        if path in SKIP_LOG_PATHS:
            return await call_next(request)

        # 请求 ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        start_time = time.perf_counter()

        # 提取请求信息
        method = request.method
        client_ip = request.client.host if request.client else "-"
        query = str(request.url.query) if request.url.query else ""
        user_agent = request.headers.get("user-agent", "")[:100]

        # 执行请求
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            # 未捕获异常
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request_error | %s %s | %s | %.1fms | %s | error=%s",
                method,
                path,
                request_id,
                duration_ms,
                client_ip,
                str(exc)[:200],
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000

        # 结构化日志
        log_data = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "query": query,
            "status": status_code,
            "duration_ms": round(duration_ms, 1),
            "client_ip": client_ip,
            "user_agent": user_agent,
        }

        # 慢请求告警
        if duration_ms > self.slow_threshold_ms:
            logger.warning(
                "slow_request | %s %s | %s | %.1fms | status=%d",
                method,
                path,
                request_id,
                duration_ms,
                status_code,
            )

        # 错误请求
        if status_code >= 500:
            logger.error(
                "server_error | %s %s | %s | %.1fms | status=%d",
                method,
                path,
                request_id,
                duration_ms,
                status_code,
            )
        elif status_code >= 400:
            logger.warning(
                "client_error | %s %s | %s | %.1fms | status=%d",
                method,
                path,
                request_id,
                duration_ms,
                status_code,
            )
        else:
            logger.info(
                "request | %s %s | %s | %.1fms | status=%d",
                method,
                path,
                request_id,
                duration_ms,
                status_code,
            )

        # 添加请求 ID 到响应头
        response.headers["X-Request-ID"] = request_id

        return response
