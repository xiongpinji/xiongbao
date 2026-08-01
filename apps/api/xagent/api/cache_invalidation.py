"""缓存失效策略：精确控制缓存生命周期。

功能：
- 标签化缓存（Tag-based Invalidation）
- 按标签批量失效
- TTL + 手动失效双模式
- LRU 淘汰 + 容量限制
- 缓存命中率统计

用法：
    from xagent.api.cache_invalidation import cache

    # 写入（带标签）
    cache.set("user:123", data, ttl=300, tags=["users", "user:123"])

    # 按标签失效
    cache.invalidate_tag("user:123")  # 只失效该用户
    cache.invalidate_tag("users")     # 失效所有用户缓存
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.cache")


@dataclass
class CacheEntry:
    """缓存条目。"""

    key: str
    value: Any
    tags: set[str]
    created_at: float
    expires_at: float | None  # None = 永不过期
    access_count: int = 0

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class TaggedCache:
    """标签化缓存（LRU + Tag Invalidation）。"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._tag_index: dict[str, set[str]] = {}  # tag → set of keys
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._stats = {"hits": 0, "misses": 0, "sets": 0, "invalidations": 0}

    def get(self, key: str) -> Any | None:
        """获取缓存（LRU 更新）。"""
        entry = self._store.get(key)
        if entry is None:
            self._stats["misses"] += 1
            return None

        if entry.is_expired:
            self._remove(key)
            self._stats["misses"] += 1
            return None

        # LRU：移到末尾
        self._store.move_to_end(key)
        entry.access_count += 1
        self._stats["hits"] += 1
        return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """写入缓存。"""
        # 如果已存在，先清理旧标签索引
        if key in self._store:
            self._remove_tag_index(key)

        now = time.time()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = now + effective_ttl if effective_ttl > 0 else None

        entry = CacheEntry(
            key=key,
            value=value,
            tags=set(tags or []),
            created_at=now,
            expires_at=expires_at,
        )

        self._store[key] = entry
        self._store.move_to_end(key)
        self._stats["sets"] += 1

        # 更新标签索引
        for tag in entry.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(key)

        # LRU 淘汰
        while len(self._store) > self._max_size:
            evicted_key, _ = self._store.popitem(last=False)
            self._remove_tag_index(evicted_key)

    def delete(self, key: str) -> bool:
        """删除单个缓存。"""
        if key in self._store:
            self._remove(key)
            return True
        return False

    def invalidate_tag(self, tag: str) -> int:
        """按标签批量失效，返回失效数量。"""
        keys = self._tag_index.pop(tag, set())
        count = 0
        for key in keys:
            if key in self._store:
                self._remove(key)
                count += 1

        self._stats["invalidations"] += count
        if count > 0:
            logger.debug("cache invalidated: tag=%s count=%d", tag, count)
        return count

    def invalidate_pattern(self, pattern: str) -> int:
        """按 key 前缀失效。"""
        keys_to_remove = [k for k in self._store if k.startswith(pattern)]
        for key in keys_to_remove:
            self._remove(key)
        self._stats["invalidations"] += len(keys_to_remove)
        return len(keys_to_remove)

    def clear(self) -> int:
        """清空所有缓存。"""
        count = len(self._store)
        self._store.clear()
        self._tag_index.clear()
        return count

    def _remove(self, key: str) -> None:
        """内部删除。"""
        entry = self._store.pop(key, None)
        if entry:
            self._remove_tag_index(key)

    def _remove_tag_index(self, key: str) -> None:
        """清理标签索引。"""
        entry = self._store.get(key)
        tags = entry.tags if entry else set()
        for tag in tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(key)
                if not self._tag_index[tag]:
                    del self._tag_index[tag]

    @property
    def stats(self) -> dict:
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0
        return {
            **self._stats,
            "size": len(self._store),
            "hit_rate": round(hit_rate, 4),
            "tags": len(self._tag_index),
        }


# 全局单例
cache = TaggedCache(max_size=2000, default_ttl=300)
