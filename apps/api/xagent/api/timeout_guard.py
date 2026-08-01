"""请求超时控制：防止长时间挂起。

功能：
- 全局请求超时（默认 30s）
- 按路径配置不同超时
- 超时返回 504 Gateway Timeout
- 长任务路径排除（SSE/WebSocket）

用法：
    from xagent.api.timeout_guard import TimeoutGuardMiddleware
    app.add_middleware(TimeoutGuardMiddleware, default_timeout=30)
"""

from __future__ import annotations

import asyncio

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.timeout")

# 路径特定超时（秒）
PATH_TIMEOUTS: dict[str, float] = {
    "/api/v1/agents/run": 120.0,  # Agent 执行允许更长
    "/api/v1/workflows/execute": 90.0,
    "/api/v1/export": 60.0,
}

# 排除路径（SSE/WS 不受超时限制）
EXCLUDE_PREFIXES = ("/ws", "/api/v1/stream", "/api/v1/runs/")


class TimeoutGuardMiddleware(BaseHTTPMiddleware):
    """请求超时保护中间件。"""

    def __init__(
        self,
        app,
        default_timeout: float = 30.0,
        path_timeouts: dict[str, float] | None = None,
        exclude_prefixes: list[str] | None = None,
    ):
        super().__init__(app)
        self.default_timeout = default_timeout
        self.path_timeouts = path_timeouts or PATH_TIMEOUTS
        self.exclude_prefixes = exclude_prefixes or EXCLUDE_PREFIXES

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # 排除长连接路径
        if any(path.startswith(p) for p in self.exclude_prefixes):
            return await call_next(request)

        # 确定超时
        timeout = self._get_timeout(path)

        try:
            response = await asyncio.wait_for(
                call_next(request), timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            logger.warning(
                "request timeout: %s %s (%.1fs)", request.method, path, timeout
            )
            return JSONResponse(
                status_code=504,
                content={
                    "error": "gateway_timeout",
                    "message": f"请求处理超时（{timeout:.0f}s），请稍后重试",
                    "timeout": timeout,
                    "path": path,
                },
            )

    def _get_timeout(self, path: str) -> float:
        """获取路径对应的超时。"""
        for prefix, timeout in self.path_timeouts.items():
            if path.startswith(prefix):
                return timeout
        return self.default_timeout
