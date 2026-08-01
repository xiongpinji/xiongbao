"""分布式锁：基于内存的互斥锁管理。

功能：
- 命名锁（按资源粒度）
- 自动过期（防死锁）
- 可重入
- 等待超时

用法：
    from xagent.api.distributed_lock import LockManager

    locks = LockManager()
    async with locks.acquire("resource:123", timeout_s=10):
        # 临界区
        ...
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from xagent.infra.logging import get_logger

logger = get_logger("xagent.lock")


@dataclass
class LockInfo:
    """锁信息。"""

    name: str
    owner: str
    acquired_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    reentrant_count: int = 1


class LockManager:
    """分布式锁管理器（内存实现）。"""

    def __init__(self, default_ttl_s: float = 30.0):
        self._locks: dict[str, LockInfo] = {}
        self._waiters: dict[str, list[asyncio.Future]] = {}
        self._mu = asyncio.Lock()
        self._default_ttl_s = default_ttl_s

        # 统计
        self._total_acquired = 0
        self._total_timeouts = 0
        self._total_contentions = 0

    @asynccontextmanager
    async def acquire(
        self,
        name: str,
        timeout_s: float = 10.0,
        ttl_s: float | None = None,
        owner: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """获取锁（上下文管理器）。

        Args:
            name: 锁名称
            timeout_s: 等待超时
            ttl_s: 锁过期时间
            owner: 持有者标识（默认自动生成）

        Yields:
            owner ID

        Raises:
            TimeoutError: 等待超时
        """
        owner_id = owner or str(uuid.uuid4())[:8]
        ttl = ttl_s or self._default_ttl_s

        acquired = await self._try_acquire(name, owner_id, ttl, timeout_s)
        if not acquired:
            self._total_timeouts += 1
            raise TimeoutError(f"Failed to acquire lock '{name}' within {timeout_s}s")

        try:
            yield owner_id
        finally:
            await self._release(name, owner_id)

    async def _try_acquire(self, name: str, owner: str, ttl: float, timeout_s: float) -> bool:
        """尝试获取锁。"""
        deadline = time.time() + timeout_s

        while True:
            async with self._mu:
                existing = self._locks.get(name)

                # 锁不存在或已过期
                if existing is None or time.time() > existing.expires_at:
                    self._locks[name] = LockInfo(
                        name=name,
                        owner=owner,
                        expires_at=time.time() + ttl,
                    )
                    self._total_acquired += 1
                    return True

                # 可重入
                if existing.owner == owner:
                    existing.reentrant_count += 1
                    existing.expires_at = time.time() + ttl
                    return True

                # 锁被占用
                self._total_contentions += 1

            # 检查超时
            if time.time() >= deadline:
                return False

            # 等待释放
            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()
            if name not in self._waiters:
                self._waiters[name] = []
            self._waiters[name].append(future)

            try:
                wait_time = min(deadline - time.time(), 0.5)
                await asyncio.wait_for(future, timeout=wait_time)
            except asyncio.TimeoutError:
                pass
            finally:
                if name in self._waiters:
                    try:
                        self._waiters[name].remove(future)
                    except ValueError:
                        pass

    async def _release(self, name: str, owner: str) -> None:
        """释放锁。"""
        async with self._mu:
            existing = self._locks.get(name)
            if existing is None or existing.owner != owner:
                return

            existing.reentrant_count -= 1
            if existing.reentrant_count > 0:
                return

            del self._locks[name]

        # 通知等待者
        waiters = self._waiters.pop(name, [])
        for future in waiters:
            if not future.done():
                future.set_result(True)

    async def is_locked(self, name: str) -> bool:
        """检查锁状态。"""
        async with self._mu:
            existing = self._locks.get(name)
            if existing is None:
                return False
            if time.time() > existing.expires_at:
                del self._locks[name]
                return False
            return True

    def get_stats(self) -> dict[str, Any]:
        """获取统计。"""
        return {
            "active_locks": len(self._locks),
            "total_acquired": self._total_acquired,
            "total_timeouts": self._total_timeouts,
            "total_contentions": self._total_contentions,
        }

    async def force_release(self, name: str) -> bool:
        """强制释放（管理用途）。"""
        async with self._mu:
            if name in self._locks:
                del self._locks[name]
                waiters = self._waiters.pop(name, [])
                for f in waiters:
                    if not f.done():
                        f.set_result(True)
                return True
            return False


# 全局实例
lock_manager = LockManager()
