"""登录限流：按 IP+用户名 计数，防口令爆破。

策略：1 分钟窗口内失败 ``max_failures`` 次 -> 锁定 ``lockout_seconds`` 秒；
锁定期间请求直接 429 + ``retry_after``。成功登录立即清零计数。

双后端（多实例部署就绪）：
- ``InMemoryBackend``（默认）：进程内滑动窗口（threading.Lock 线程安全），
  lite / 单实例适用。
- ``RedisBackend``：``get_login_rate_limiter()`` 检测到
  ``XAGENT_CACHE__REDIS_URL`` 后自动启用；计数与锁定状态存 Redis（带 TTL
  的滑动窗口，key 前缀 ``xagent:login_rl:``），多实例共享限流状态。
  Redis 调用失败时降级为进程内存并打 warning（限流不中断，但多实例下
  计数退化为各自统计）。
"""

from __future__ import annotations

import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from functools import lru_cache

from xagent.infra.logging import get_logger

logger = get_logger("xagent.auth.login_rate_limit")


class LoginRateLimitBackend(ABC):
    """登录限流后端抽象接口（异步）。

    三个方法语义与 ``LoginRateLimiter`` 的同步同名方法一致。
    """

    @abstractmethod
    async def locked_seconds(self, key: str) -> float:
        """剩余锁定秒数；未锁定返回 0。"""

    @abstractmethod
    async def record_failure(self, key: str) -> float:
        """记录一次失败；若因此进入锁定，返回锁定时长，否则返回 0。"""

    @abstractmethod
    async def record_success(self, key: str) -> None:
        """登录成功：清零失败计数与锁定状态。"""


class InMemoryBackend(LoginRateLimitBackend):
    """进程内滑动窗口后端（默认；Redis 不可用时的降级目标）。"""

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

    # 同步核心（带 now 便于单测控制时间）
    def locked_seconds_sync(self, key: str, now: float | None = None) -> float:
        now = time.time() if now is None else now
        with self._lock:
            until = self._locked_until.get(key, 0.0)
            if until <= now:
                self._locked_until.pop(key, None)
                return 0.0
            return until - now

    def record_failure_sync(self, key: str, now: float | None = None) -> float:
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

    def record_success_sync(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    # 异步接口（协议要求）
    async def locked_seconds(self, key: str) -> float:
        return self.locked_seconds_sync(key)

    async def record_failure(self, key: str) -> float:
        return self.record_failure_sync(key)

    async def record_success(self, key: str) -> None:
        self.record_success_sync(key)


class RedisBackend(LoginRateLimitBackend):
    """Redis 滑动窗口后端：多实例共享限流状态。

    - 失败计数：有序集合（score=毫秒时间戳），ZREMRANGEBYSCORE 滑窗 + ZADD，
      key 带 PEXPIRE=window，自然过期。
    - 锁定标记：``SET lock_key 1 PX lockout``，剩余锁定时间读 PTTL。
    - Redis 调用异常：打 warning 并降级到进程内存 ``_fallback``
      （限流功能不中断；多实例下计数退化为各实例独立统计）。
    """

    KEY_PREFIX = "xagent:login_rl:"

    def __init__(
        self,
        redis_url: str,
        max_failures: int = 5,
        window_seconds: int = 60,
        lockout_seconds: int = 60,
        *,
        client=None,
    ) -> None:
        if client is not None:
            self._client = client  # 测试注入（fakeredis / mock）
        else:
            import redis.asyncio as aioredis  # 延迟导入，lite 模式无需 redis 服务

            self._client = aioredis.from_url(redis_url, decode_responses=True)
        self._max_failures = max_failures
        self._window_ms = window_seconds * 1000
        self._lockout_seconds = lockout_seconds
        self._lockout_ms = lockout_seconds * 1000
        self._fallback = InMemoryBackend(max_failures, window_seconds, lockout_seconds)

    def _count_key(self, key: str) -> str:
        return f"{self.KEY_PREFIX}fail:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self.KEY_PREFIX}lock:{key}"

    async def locked_seconds(self, key: str) -> float:
        try:
            ttl_ms = await self._client.pttl(self._lock_key(key))
            if ttl_ms <= 0:
                return 0.0
            return ttl_ms / 1000.0
        except Exception as exc:  # noqa: BLE001
            logger.warning("login_rate_limit_redis_error", op="locked_seconds", error=str(exc))
            return await self._fallback.locked_seconds(key)

    async def record_failure(self, key: str) -> float:
        count_key = self._count_key(key)
        try:
            now_ms = int(time.time() * 1000)
            member = f"{now_ms}:{uuid.uuid4().hex[:8]}"
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(count_key, 0, now_ms - self._window_ms)
                pipe.zadd(count_key, {member: now_ms})
                pipe.zcard(count_key)
                pipe.pexpire(count_key, self._window_ms)
                results = await pipe.execute()
            count = int(results[2])
            if count >= self._max_failures:
                await self._client.set(self._lock_key(key), "1", px=self._lockout_ms)
                await self._client.delete(count_key)
                return float(self._lockout_seconds)
            return 0.0
        except Exception as exc:  # noqa: BLE001
            logger.warning("login_rate_limit_redis_error", op="record_failure", error=str(exc))
            return await self._fallback.record_failure(key)

    async def record_success(self, key: str) -> None:
        try:
            await self._client.delete(self._count_key(key), self._lock_key(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("login_rate_limit_redis_error", op="record_success", error=str(exc))
            await self._fallback.record_success(key)


class LoginRateLimiter:
    """滑动窗口失败计数 + 锁定的登录限流器。

    - 同步方法（``locked_seconds`` / ``record_failure`` / ``record_success``，
      支持 ``now`` 注入）始终作用于内存实现，供单元测试与同步上下文使用。
    - 异步方法（``alocked_seconds`` / ``arecord_failure`` / ``arecord_success``）
      是 FastAPI 路由应使用的入口：配置了 Redis 后端时走 Redis（多实例共享），
      否则走内存实现。
    """

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: int = 60,
        lockout_seconds: int = 60,
        *,
        backend: LoginRateLimitBackend | None = None,
    ) -> None:
        self._memory = InMemoryBackend(max_failures, window_seconds, lockout_seconds)
        self._backend = backend

    @property
    def backend_name(self) -> str:
        """当前生效的异步后端名（监控/排障用）。"""
        return type(self._backend).__name__ if self._backend is not None else "InMemoryBackend"

    @staticmethod
    def make_key(ip: str, username: str) -> str:
        """限流键：客户端 IP + 用户名（防单账号爆破也防分布式试探）。"""
        return f"{ip}:{username.strip().lower()}"

    # ─── 同步接口（内存实现，保持原有契约）─────────────────────────────

    def locked_seconds(self, key: str, now: float | None = None) -> float:
        """剩余锁定秒数；未锁定返回 0。"""
        return self._memory.locked_seconds_sync(key, now)

    def record_failure(self, key: str, now: float | None = None) -> float:
        """记录一次失败；若因此进入锁定，返回锁定时长，否则返回 0。"""
        return self._memory.record_failure_sync(key, now)

    def record_success(self, key: str) -> None:
        """登录成功：清零失败计数与锁定状态。"""
        self._memory.record_success_sync(key)

    # ─── 异步接口（路由入口；有 Redis 后端时多实例共享）─────────────────

    async def alocked_seconds(self, key: str) -> float:
        if self._backend is not None:
            return await self._backend.locked_seconds(key)
        return await self._memory.locked_seconds(key)

    async def arecord_failure(self, key: str) -> float:
        if self._backend is not None:
            return await self._backend.record_failure(key)
        return await self._memory.record_failure(key)

    async def arecord_success(self, key: str) -> None:
        if self._backend is not None:
            await self._backend.record_success(key)
        else:
            await self._memory.record_success(key)


@lru_cache
def get_login_rate_limiter() -> LoginRateLimiter:
    """全局单例。测试可用 ``reset_login_rate_limiter()`` 重置。

    配置了 ``XAGENT_CACHE__REDIS_URL`` 时自动启用 Redis 后端（多实例共享限流），
    否则使用进程内实现（lite / 单实例默认）。
    """
    from xagent.infra.settings import get_settings

    redis_url = get_settings().cache.redis_url
    if redis_url:
        logger.info("login_rate_limit_redis_backend", redis_url=redis_url.split("@")[-1])
        return LoginRateLimiter(backend=RedisBackend(redis_url))
    return LoginRateLimiter()


def reset_login_rate_limiter() -> None:
    get_login_rate_limiter.cache_clear()
