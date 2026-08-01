"""Qdrant 向量库实现。

- qdrant_url 非空 -> 连接远程 Qdrant（full 模式）。
- qdrant_url 为空 -> 使用 qdrant-client 的 ``:memory:`` 内存模式（lite 模式）。
租户隔离：以 metadata.tenant_id 字段过滤检索。
"""

from __future__ import annotations

import uuid
from typing import Any

from xagent.adapters.memory.base import Embedder, MemoryRecord, SearchHit, VectorStore
from xagent.infra.settings import MemorySettings


class QdrantVectorStore(VectorStore):
    def __init__(self, cfg: MemorySettings, embedder: Embedder) -> None:
        from qdrant_client import AsyncQdrantClient

        self._cfg = cfg
        self._embedder = embedder
        self._collection = cfg.collection
        if cfg.qdrant_url:
            self._client = AsyncQdrantClient(
                url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None
            )
        else:
            # 本地磁盘模式：数据持久化到项目目录（重启不丢失）
            from pathlib import Path
            db_path = str(Path(__file__).resolve().parents[4] / "data" / "qdrant")
            self._client = AsyncQdrantClient(path=db_path)
        self._ready = False

    async def ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        if self._ready:
            return
        existing = await self._client.get_collections()
        names = {c.name for c in existing.collections}
        if self._collection not in names:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._embedder.dim, distance=Distance.COSINE
                ),
            )
        self._ready = True

    async def upsert(self, records: list[MemoryRecord]) -> None:
        from qdrant_client.models import PointStruct

        await self.ensure_collection()
        vectors = await self._embedder.embed([r.text for r in records])
        points = [
            PointStruct(
                id=self._point_id(r.id),
                vector=vec,
                payload={"text": r.text, "ref_id": r.id, **r.metadata},
            )
            for r, vec in zip(records, vectors, strict=True)
        ]
        await self._client.upsert(collection_name=self._collection, points=points)

    async def search(
        self, query: str, *, top_k: int = 5, tenant_id: str | None = None
    ) -> list[SearchHit]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self.ensure_collection()
        vec = (await self._embedder.embed([query]))[0]
        query_filter = None
        if tenant_id:
            query_filter = Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
            )
        results = await self._client.query_points(
            collection_name=self._collection,
            query=vec,
            limit=top_k,
            query_filter=query_filter,
        )
        hits: list[SearchHit] = []
        for r in results.points:
            payload: dict[str, Any] = r.payload or {}
            hits.append(
                SearchHit(
                    id=payload.get("ref_id", str(r.id)),
                    text=payload.get("text", ""),
                    score=r.score,
                    metadata={
                        k: v for k, v in payload.items() if k not in ("text", "ref_id")
                    },
                )
            )
        return hits

    async def health(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:
            return False

    @staticmethod
    def _point_id(ref_id: str) -> str:
        # Qdrant 要求 point id 为 uuid/int；用确定性 uuid5 由业务 id 派生
        return str(uuid.uuid5(uuid.NAMESPACE_URL, ref_id))
