"""分布式锁：基于内存的互斥锁管理。

功能：
- 异步锁（asyncio.Lock 封装）
- 自动过期（防死锁）
- 锁持有者标识
- 上下文管理器 + 装饰器

用法：
    from xagent.api.distributed_lock import lock_manager

    # 上下文管理器
    async with lock_manager.acquire("resource:123", timeout=30):
        do_exclusive_work()

    # 装饰器
    @lock_manager.lock("task:{task_id}")
    async def process_task(task_id: str): ...
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, AsyncGenerator, Callable

from xagent.infra.logging import get_logger

logger = get_logger("xagent.lock")


@dataclass
class LockInfo:
    """锁信息。"""

    key: str
    owner: str
    acquired_at: float
    timeout: float  # 秒
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def is_expired(self) -> bool:
        return time.time() - self.acquired_at > self.timeout


class LockManager:
    """异步锁管理器。

    注意：这是进程内锁，适用于单实例部署。
    多实例需替换为 Redis 分布式锁。
    """

    def __init__(self, default_timeout: float = 30.0):
        self._locks: dict[str, LockInfo] = {}
        self._default_timeout = default_timeout
        self._stats = {"acquired": 0, "released": 0, "timeouts": 0, "contentions": 0}

    @asynccontextmanager
    async def acquire(
        self,
        key: str,
        timeout: float | None = None,
        owner: str | None = None,
        wait_timeout: float = 10.0,
    ) -> AsyncGenerator[str, None]:
        """获取锁（上下文管理器）。

        Args:
            key: 锁标识
            timeout: 锁自动过期时间（秒）
            owner: 持有者标识
            wait_timeout: 等待获取锁的超时（秒）

        Yields:
            owner ID
        """
        effective_timeout = timeout or self._default_timeout
        effective_owner = owner or str(uuid.uuid4())[:8]

        # 检查过期锁
        if key in self._locks and self._locks[key].is_expired:
            logger.warning("lock expired, force releasing: %s", key)
            self._locks[key].lock.release()
            del self._locks[key]
            self._stats["timeouts"] += 1

        # 获取或创建锁
        if key not in self._locks:
            self._locks[key] = LockInfo(
                key=key,
                owner=effective_owner,
                acquired_at=time.time(),
                timeout=effective_timeout,
            )

        lock_info = self._locks[key]

        # 等待获取
        if lock_info.lock.locked():
            self._stats["contentions"] += 1

        try:
            await asyncio.wait_for(lock_info.lock.acquire(), timeout=wait_timeout)
        except asyncio.TimeoutError:
            logger.warning("lock acquisition timeout: %s", key)
            raise TimeoutError(f"Failed to acquire lock '{key}' within {wait_timeout}s")

        # 更新持有者信息
        lock_info.owner = effective_owner
        lock_info.acquired_at = time.time()
        lock_info.timeout = effective_timeout
        self._stats["acquired"] += 1

        logger.debug("lock acquired: %s by %s", key, effective_owner)

        try:
            yield effective_owner
        finally:
            lock_info.lock.release()
            self._stats["released"] += 1
            # 如果没有其他等待者，清理
            if not lock_info.lock.locked():
                del self._locks[key]
            logger.debug("lock released: %s", key)

    def lock(self, key_template: str, timeout: float | None = None):
        """锁装饰器。

        key_template 支持格式化：@lock("task:{task_id}")
        """

        def decorator(fn: Callable) -> Callable:
            @wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                # 解析 key
                try:
                    key = key_template.format(*args, **kwargs)
                except (KeyError, IndexError):
                    key = key_template

                async with self.acquire(key, timeout=timeout):
                    return await fn(*args, **kwargs)

            return wrapper

        return decorator

    def is_locked(self, key: str) -> bool:
        """检查锁是否被持有。"""
        info = self._locks.get(key)
        if info is None:
            return False
        if info.is_expired:
            return False
        return info.lock.locked()

    def get_lock_info(self, key: str) -> dict | None:
        """获取锁信息。"""
        info = self._locks.get(key)
        if info is None:
            return None
        return {
            "key": info.key,
            "owner": info.owner,
            "acquired_at": info.acquired_at,
            "timeout": info.timeout,
            "is_expired": info.is_expired,
            "locked": info.lock.locked(),
        }

    @property
    def stats(self) -> dict:
        return {**self._stats, "active_locks": len(self._locks)}


# 全局单例
lock_manager = LockManager(default_timeout=30.0)
