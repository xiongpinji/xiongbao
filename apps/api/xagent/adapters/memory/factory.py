"""记忆 / 向量库工厂。

- Embedder：有 LLM provider key -> LiteLLMEmbedder，否则 HashEmbedder（离线降级）。
- VectorStore：Qdrant（远程或内存模式）。
嵌入降级时维度用 HashEmbedder 自身维度，保证与集合创建一致。
"""

from __future__ import annotations

from functools import lru_cache

from xagent.adapters.memory.base import Embedder, VectorStore
from xagent.adapters.memory.embedder import HashEmbedder, LiteLLMEmbedder
from xagent.adapters.memory.qdrant_store import QdrantVectorStore
from xagent.infra.settings import get_settings


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    key = settings.llm.openai_api_key
    proxy = settings.llm.proxy_url
    if key or proxy:
        return LiteLLMEmbedder(
            settings.memory,
            api_key=key,
            proxy_url=proxy,
            proxy_api_key=settings.llm.proxy_api_key,
        )
    return HashEmbedder(dim=256)


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return QdrantVectorStore(settings.memory, get_embedder())


def reset_memory() -> None:
    get_embedder.cache_clear()
    get_vector_store.cache_clear()
