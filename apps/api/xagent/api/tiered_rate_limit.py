"""精细化限流：按租户/端点/用户分级限流。

策略：
- 全局限流：所有请求 300/min（已有 RateLimitMiddleware）
- 租户级：每租户 200/min
- 用户级：每用户 100/min
- 端点级：敏感端点（login）20/min

用法：
    from xagent.api.tiered_rate_limit import TieredRateLimiter
    limiter = get_tiered_limiter()
    await limiter.check(tenant_id, user_id, path)
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException, status


@dataclass
class RateLimitTier:
    """限流层级配置。"""

    max_requests: int
    window_seconds: int = 60


# 默认层级配置
TIERS = {
    "global": RateLimitTier(max_requests=1000, window_seconds=60),
    "tenant": RateLimitTier(max_requests=200, window_seconds=60),
    "user": RateLimitTier(max_requests=100, window_seconds=60),
    "sensitive": RateLimitTier(max_requests=20, window_seconds=60),
}

# 敏感端点列表
SENSITIVE_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/reset-password",
}


@dataclass
class _Window:
    count: int = 0
    reset_at: float = 0.0


class TieredRateLimiter:
    """多层限流器。"""

    def __init__(self) -> None:
        self._tenant_windows: dict[str, _Window] = defaultdict(_Window)
        self._user_windows: dict[str, _Window] = defaultdict(_Window)
        self._path_windows: dict[str, _Window] = defaultdict(_Window)

    def _check_window(self, key: str, store: dict[str, _Window], tier: RateLimitTier) -> bool:
        """检查并更新窗口计数。返回 True 表示通过。"""
        now = time.time()
        w = store[key]
        if now >= w.reset_at:
            w.count = 0
            w.reset_at = now + tier.window_seconds
        w.count += 1
        return w.count <= tier.max_requests

    async def check(self, tenant_id: str, user_id: str, path: str) -> None:
        """执行多层限流检查。超限抛 429。"""
        # 租户级
        if not self._check_window(tenant_id, self._tenant_windows, TIERS["tenant"]):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"租户限流：{TIERS['tenant'].max_requests} req/{TIERS['tenant'].window_seconds}s",
                headers={"Retry-After": "60"},
            )

        # 用户级
        user_key = f"{tenant_id}:{user_id}"
        if not self._check_window(user_key, self._user_windows, TIERS["user"]):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"用户限流：{TIERS['user'].max_requests} req/{TIERS['user'].window_seconds}s",
                headers={"Retry-After": "60"},
            )

        # 敏感端点级
        if path in SENSITIVE_PATHS:
            path_key = f"{user_key}:{path}"
            if not self._check_window(path_key, self._path_windows, TIERS["sensitive"]):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"敏感端点限流：{TIERS['sensitive'].max_requests} req/{TIERS['sensitive'].window_seconds}s",
                    headers={"Retry-After": "60"},
                )

    def stats(self) -> dict:
        return {
            "tenant_windows": len(self._tenant_windows),
            "user_windows": len(self._user_windows),
            "path_windows": len(self._path_windows),
            "tiers": {k: {"max": v.max_requests, "window": v.window_seconds} for k, v in TIERS.items()},
        }


_limiter: TieredRateLimiter | None = None


def get_tiered_limiter() -> TieredRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = TieredRateLimiter()
    return _limiter
