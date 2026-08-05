"""RAG 知识库：文档上传 → 分块 → 向量化 → 语义检索 → Agent 上下文注入。"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.knowledge")

# 分块参数
CHUNK_SIZE = 800  # 每块最大字符数
CHUNK_OVERLAP = 100  # 重叠字符数


@dataclass
class Document:
    """知识库文档元数据。"""
    doc_id: str
    title: str
    tenant_id: str
    source: str = "upload"  # upload | url | manual
    content_type: str = "text/plain"
    chunk_count: int = 0
    created_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """智能分块：按段落优先，超长段落按句子切分。"""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            # 段落本身超长 → 按句子切
            if len(para) > chunk_size:
                sentences = _split_sentences(para)
                sub = ""
                for sent in sentences:
                    if len(sub) + len(sent) + 1 <= chunk_size:
                        sub = f"{sub} {sent}" if sub else sent
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = sent
                if sub:
                    current = sub
            else:
                current = para

    if current:
        chunks.append(current)

    # 添加重叠
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:]
            overlapped.append(prev_tail + chunks[i])
        chunks = overlapped

    return chunks


def _split_sentences(text: str) -> list[str]:
    """简单句子切分。"""
    import re
    parts = re.split(r'(?<=[。！？.!?])\s*', text)
    return [p for p in parts if p.strip()]


class KnowledgeBase:
    """知识库管理器：文档 CRUD + 向量索引 + 语义检索。"""

    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}

    async def ingest(
        self,
        text: str,
        title: str,
        tenant_id: str,
        *,
        source: str = "upload",
        content_type: str = "text/plain",
        tags: list[str] | None = None,
    ) -> Document:
        """上传文档 → 分块 → 向量化入库。"""
        from xagent.adapters.memory import MemoryRecord, get_vector_store

        doc_id = uuid.uuid4().hex[:12]
        chunks = chunk_text(text)

        # 向量化
        records = [
            MemoryRecord(
                id=f"{doc_id}_c{i}",
                text=chunk,
                metadata={
                    "doc_id": doc_id,
                    "title": title,
                    "tenant_id": tenant_id,
                    "chunk_index": i,
                    "source": source,
                    # 知识库专属标记：与会话记忆共用向量集合，检索时按此过滤，
                    # 避免知识库搜索返回会话记忆内容
                    "kind": "knowledge",
                },
            )
            for i, chunk in enumerate(chunks)
        ]
        store = get_vector_store()
        await store.ensure_collection()
        await store.upsert(records)

        doc = Document(
            doc_id=doc_id,
            title=title,
            tenant_id=tenant_id,
            source=source,
            content_type=content_type,
            chunk_count=len(chunks),
            tags=tags or [],
        )
        self._docs[doc_id] = doc
        # 持久化到 SQLite
        try:
            from xagent.core.persistence import save_chunks, save_document
            await save_document({
                "doc_id": doc_id, "tenant_id": tenant_id, "title": title,
                "source": source, "chunk_count": len(chunks), "tags": tags or [],
            })
            await save_chunks(doc_id, tenant_id, chunks)
        except Exception:  # noqa: S110
            pass
        logger.info(
            "knowledge_ingested", doc_id=doc_id, title=title,
            chunks=len(chunks), tenant_id=tenant_id,
        )
        return doc

    async def search(
        self, query: str, tenant_id: str, *, top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """语义检索知识库（只返回入库文档，不返回会话记忆）。"""
        from xagent.adapters.memory import get_vector_store

        store = get_vector_store()
        # 向量集合与会话记忆共用：多拉取后过滤，只保留知识库文档 chunks
        hits = await store.search(query, top_k=top_k * 4, tenant_id=tenant_id)
        results = [
            {
                "text": h.text,
                "score": h.score,
                "doc_id": h.metadata.get("doc_id", ""),
                "title": h.metadata.get("title", ""),
                "chunk_index": h.metadata.get("chunk_index", 0),
            }
            for h in hits
            if h.metadata.get("doc_id")
        ]
        return results[:top_k]

    def list_docs(self, tenant_id: str) -> list[Document]:
        return [d for d in self._docs.values() if d.tenant_id == tenant_id]

    async def alist_docs(self, tenant_id: str) -> list[Document]:
        """列出文档（先从 SQLite 持久层合并，保证重启后/跨进程不丢）。"""
        try:
            from xagent.core.persistence import load_documents

            for d in await load_documents(tenant_id):
                if d["doc_id"] not in self._docs:
                    self._docs[d["doc_id"]] = Document(
                        doc_id=d["doc_id"],
                        title=d["title"],
                        tenant_id=d["tenant_id"],
                        source=d["source"],
                        chunk_count=d["chunk_count"],
                        tags=d["tags"],
                        created_at=d["created_at"],
                    )
        except Exception:  # noqa: S110  持久层不可用时退回内存列表
            pass
        return self.list_docs(tenant_id)

    def get_doc(self, doc_id: str, tenant_id: str) -> Document | None:
        doc = self._docs.get(doc_id)
        if doc and doc.tenant_id == tenant_id:
            return doc
        return None

    def delete_doc(self, doc_id: str, tenant_id: str) -> bool:
        doc = self._docs.get(doc_id)
        if not doc or doc.tenant_id != tenant_id:
            return False
        del self._docs[doc_id]
        # 注意：向量库中的 chunks 暂不删除（需 Qdrant filter delete）
        return True

    async def build_context(
        self, query: str, tenant_id: str, *, max_chunks: int = 3,
    ) -> str:
        """为 Agent 构建 RAG 上下文注入文本。"""
        results = await self.search(query, tenant_id, top_k=max_chunks)
        if not results:
            return ""
        parts = [
            f"[知识库参考 {i+1}] (来源: {r['title']})\n{r['text']}"
            for i, r in enumerate(results)
        ]
        return "\n\n---\n\n".join(parts)


_kb: KnowledgeBase | None = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb
