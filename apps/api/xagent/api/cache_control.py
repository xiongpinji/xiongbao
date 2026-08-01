"""响应缓存控制：Cache-Control 头管理。

功能：
- 按路径/方法设置缓存策略
- 预设策略（静态/动态/私有）
- Vary 头自动管理
- 中间件模式

用法：
    from xagent.api.cache_control import CacheControlMiddleware, CachePolicy

    app.add_middleware(CacheControlMiddleware, policies={
        "/api/v1/models": CachePolicy.PUBLIC,
        "/api/v1/users": CachePolicy.PRIVATE,
    })
"""

from __future__ import annotations

from enum import Enum

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from xagent.infra.logging import get_logger

logger = get_logger("xagent.cache_ctrl")


class CachePolicy(str, Enum):
    """预设缓存策略。"""

    PUBLIC = "public"  # 公共缓存（CDN 可缓存）
    PRIVATE = "private"  # 仅浏览器缓存
    NO_CACHE = "no_cache"  # 每次验证
    NO_STORE = "no_store"  # 禁止缓存
    IMMUTABLE = "immutable"  # 长期不变


# 策略 → Cache-Control 值
POLICY_HEADERS: dict[CachePolicy, str] = {
    CachePolicy.PUBLIC: "public, max-age=3600, stale-while-revalidate=86400",
    CachePolicy.PRIVATE: "private, max-age=300",
    CachePolicy.NO_CACHE: "no-cache, must-revalidate",
    CachePolicy.NO_STORE: "no-store",
    CachePolicy.IMMUTABLE: "public, max-age=31536000, immutable",
}

# 默认路径策略
DEFAULT_POLICIES: dict[str, CachePolicy] = {
    "/api/v1/models": CachePolicy.PUBLIC,
    "/api/v1/health": CachePolicy.NO_STORE,
    "/static/": CachePolicy.IMMUTABLE,
    "/api/v1/agents": CachePolicy.PRIVATE,
}

# 安全方法才缓存
CACHEABLE_METHODS = {"GET", "HEAD"}


class CacheControlMiddleware(BaseHTTPMiddleware):
    """缓存控制中间件。"""

    def __init__(
        self,
        app,
        policies: dict[str, CachePolicy] | None = None,
        default_policy: CachePolicy = CachePolicy.NO_CACHE,
        vary: list[str] | None = None,
    ):
        super().__init__(app)
        self.policies = policies or DEFAULT_POLICIES
        self.default_policy = default_policy
        self.vary = vary or ["Accept", "Authorization"]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # 仅对可缓存方法设置
        if request.method not in CACHEABLE_METHODS:
            response.headers["Cache-Control"] = "no-store"
            return response

        # 已有 Cache-Control 不覆盖
        if "cache-control" in response.headers:
            return response

        path = request.url.path
        policy = self._resolve_policy(path)
        response.headers["Cache-Control"] = POLICY_HEADERS[policy]

        # Vary 头
        if policy in (CachePolicy.PUBLIC, CachePolicy.PRIVATE):
            response.headers["Vary"] = ", ".join(self.vary)

        return response

    def _resolve_policy(self, path: str) -> CachePolicy:
        """匹配路径策略（最长前缀优先）。"""
        best_match = ""
        best_policy = self.default_policy

        for prefix, policy in self.policies.items():
            if path.startswith(prefix) and len(prefix) > len(best_match):
                best_match = prefix
                best_policy = policy

        return best_policy


def cache_headers(policy: CachePolicy) -> dict[str, str]:
    """手动获取缓存头（用于路由级别）。"""
    return {"Cache-Control": POLICY_HEADERS[policy]}
