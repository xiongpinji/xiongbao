"""登录限流：按 IP+用户名 计数，防口令爆破。

策略：1 分钟窗口内失败 ``max_failures`` 次 -> 锁定 ``lockout_seconds`` 秒；
锁定期间请求直接 429 + ``retry_after``。成功登录立即清零计数。

进程内实现（threading.Lock 线程安全），lite/单实例默认；
多实例部署时应换 Redis 后端（与 RateLimitMiddleware 同一演进路径）。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from functools import lru_cache


class LoginRateLimiter:
    """滑动窗口失败计数 + 锁定的登录限流器。"""

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: int = 60,
        lockout_seconds: int = 60,
    ) -> None:
        self._max_failures = max_failures
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def make_key(ip: str, username: str) -> str:
        """限流键：客户端 IP + 用户名（防单账号爆破也防分布式试探）。"""
        return f"{ip}:{username.strip().lower()}"

    def locked_seconds(self, key: str, now: float | None = None) -> float:
        """剩余锁定秒数；未锁定返回 0。"""
        now = time.time() if now is None else now
        with self._lock:
            until = self._locked_until.get(key, 0.0)
            if until <= now:
                self._locked_until.pop(key, None)
                return 0.0
            return until - now

    def record_failure(self, key: str, now: float | None = None) -> float:
        """记录一次失败；若因此进入锁定，返回锁定时长，否则返回 0。"""
        now = time.time() if now is None else now
        with self._lock:
            bucket = self._failures[key]
            while bucket and now - bucket[0] > self._window:
                bucket.popleft()
            bucket.append(now)
            if len(bucket) >= self._max_failures:
                self._locked_until[key] = now + self._lockout
                bucket.clear()
                return float(self._lockout)
            return 0.0

    def record_success(self, key: str) -> None:
        """登录成功：清零失败计数与锁定状态。"""
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)


@lru_cache
def get_login_rate_limiter() -> LoginRateLimiter:
    """全局单例。测试可用 ``reset_login_rate_limiter()`` 重置。"""
    return LoginRateLimiter()


def reset_login_rate_limiter() -> None:
    get_login_rate_limiter.cache_clear()
