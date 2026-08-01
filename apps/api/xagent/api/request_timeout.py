"""请求超时：为下游处理设置硬性超时。

功能：
- 按路由配置超时
- 超时后返回 504
- 超时预警头
- 支持取消正在执行的任务

用法：
    from xagent.api.request_timeout import TimeoutMiddleware

    app.add_middleware(TimeoutMiddleware, default_timeout_s=30)
"""

from __future__ import annotations

import asyncio
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.timeout")


class TimeoutMiddleware(BaseHTTPMiddleware):
    """请求超时中间件。"""

    def __init__(
        self,
        app,
        default_timeout_s: float = 30.0,
        route_timeouts: dict[str, float] | None = None,
        exclude_prefixes: list[str] | None = None,
        warn_threshold_pct: float = 80.0,
    ):
        super().__init__(app)
        self.default_timeout_s = default_timeout_s
        self.route_timeouts = route_timeouts or {}
        self.exclude_prefixes = exclude_prefixes or ["/health", "/ws"]
        self.warn_threshold_pct = warn_threshold_pct

    def _get_timeout(self, path: str) -> float:
        """获取路由超时配置。"""
        # 精确匹配
        if path in self.route_timeouts:
            return self.route_timeouts[path]
        # 前缀匹配
        for prefix, timeout in self.route_timeouts.items():
            if path.startswith(prefix):
                return timeout
        return self.default_timeout_s

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # 排除路径
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        timeout_s = self._get_timeout(path)
        start = time.time()

        try:
            response = await asyncio.wait_for(
                call_next(request),
                timeout=timeout_s,
            )

            # 添加耗时头
            elapsed = time.time() - start
            response.headers["X-Response-Time-Ms"] = str(round(elapsed * 1000, 1))

            # 超时预警
            if elapsed / timeout_s * 100 >= self.warn_threshold_pct:
                response.headers["X-Timeout-Warning"] = f"{elapsed:.1f}s/{timeout_s}s"
                logger.warning(
                    "slow request: %s %s took %.1fs (limit %.1fs)",
                    request.method, path, elapsed, timeout_s,
                )

            return response

        except asyncio.TimeoutError:
            elapsed = time.time() - start
            logger.error(
                "request timeout: %s %s after %.1fs (limit %.1fs)",
                request.method, path, elapsed, timeout_s,
            )
            return JSONResponse(
                status_code=504,
                content={
                    "error": "gateway_timeout",
                    "detail": f"Request exceeded {timeout_s}s limit",
                    "elapsed_s": round(elapsed, 2),
                },
                headers={"Retry-After": "5"},
            )
