"""请求染色：流量标记与路由。

功能：
- 为请求添加颜色标签（blue/green/canary）
- 按染色路由到不同后端
- 染色传播（下游继承）
- 调试/测试流量隔离

用法：
    from xagent.api.request_coloring import ColoringMiddleware, get_color

    app.add_middleware(ColoringMiddleware, rules={
        "x-test-user": "canary",
        "x-internal": "green",
    })
    # 业务代码中：
    color = get_color()  # 当前请求颜色
"""

from __future__ import annotations

from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.coloring")

# 请求级颜色
_color_var: ContextVar[str] = ContextVar("request_color", default="blue")

HEADER_COLOR = "X-Traffic-Color"

# 预定义颜色
COLOR_BLUE = "blue"  # 稳定版
COLOR_GREEN = "green"  # 新版
COLOR_CANARY = "canary"  # 金丝雀
COLOR_SHADOW = "shadow"  # 影子流量（不产生副作用）


def get_color() -> str:
    """获取当前请求颜色。"""
    return _color_var.get()


def set_color(color: str) -> None:
    """手动设置颜色。"""
    _color_var.set(color)


class ColoringMiddleware(BaseHTTPMiddleware):
    """请求染色中间件。"""

    def __init__(
        self,
        app,
        rules: dict[str, str] | None = None,
        default_color: str = COLOR_BLUE,
        header_rules: dict[str, str] | None = None,
    ):
        """
        Args:
            rules: {请求头名: 颜色} — 存在该头即染色
            header_rules: {请求头名: 颜色} — 同上（别名）
            default_color: 默认颜色
        """
        super().__init__(app)
        self.rules = rules or header_rules or {}
        self.default_color = default_color

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 确定颜色
        color = self.default_color

        # 从请求头继承
        incoming_color = request.headers.get(HEADER_COLOR)
        if incoming_color:
            color = incoming_color

        # 规则匹配
        for header_name, header_color in self.rules.items():
            if request.headers.get(header_name):
                color = header_color
                break

        # 设置上下文
        token = _color_var.set(color)

        try:
            response = await call_next(request)
            response.headers[HEADER_COLOR] = color
            return response
        finally:
            _color_var.reset(token)


def propagation_headers() -> dict[str, str]:
    """获取传播头（传给下游服务）。"""
    return {HEADER_COLOR: get_color()}


def is_shadow() -> bool:
    """是否为影子流量。"""
    return get_color() == COLOR_SHADOW
