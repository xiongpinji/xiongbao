"""记忆 / 向量适配层抽象：向量库 upsert / search + 嵌入。

Phase 0 提供最小可用的向量存储接口；Phase 1 在其上叠加 Mem0/Graphiti
的高层记忆语义（会话记忆、时序图）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class MemoryRecord:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchHit:
    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dim(self) -> int: ...


@runtime_checkable
class VectorStore(Protocol):
    """向量库抽象。"""

    async def ensure_collection(self) -> None: ...
    async def upsert(self, records: list[MemoryRecord]) -> None: ...
    async def search(
        self, query: str, *, top_k: int = 5, tenant_id: str | None = None
    ) -> list[SearchHit]: ...
    async def health(self) -> bool: ...
