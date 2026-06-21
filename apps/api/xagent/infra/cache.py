"""缓存：Redis 客户端，空 URL 时降级为进程内存缓存（lite 模式）。

统一暴露 ``Cache`` Protocol 风格接口（get/set/delete/ping），
``get_cache()`` 据配置返回 RedisCache 或 InMemoryCache 单例。
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

from xagent.infra.settings import get_settings


@runtime_checkable
class Cache(Protocol):
    """缓存抽象接口。"""

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def ping(self) -> bool: ...


class InMemoryCache:
    """进程内存缓存（lite / 测试 / Redis 不可用时的降级）。"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}

    async def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def ping(self) -> bool:
        return True


class RedisCache:
    """Redis 后端缓存（full 模式）。"""

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as redis  # 延迟导入，lite 模式无需 redis 服务

        self._client = redis.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        await self._client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False


_cache: Cache | None = None


def get_cache() -> Cache:
    """据配置返回缓存单例。空 redis_url => 内存缓存。"""
    global _cache
    if _cache is None:
        settings = get_settings()
        if settings.cache.redis_url:
            _cache = RedisCache(settings.cache.redis_url)
        else:
            _cache = InMemoryCache()
    return _cache


def reset_cache() -> None:
    """测试用：重置缓存单例。"""
    global _cache
    _cache = None
