"""LightRAG 轻量 RAG 适配器（文档知识库检索）。

在 Mem0（会话记忆）+ Graphiti（图谱记忆）基础上补充文档知识检索能力。
支持 5 种检索模式（local/global/hybrid/naive/mix），增量更新。
"""

from __future__ import annotations

from functools import lru_cache

from xagent.infra.logging import get_logger
from xagent.infra.paths import data_path

logger = get_logger("xagent.knowledge")


class KnowledgeRetriever:
    """LightRAG 文档知识库检索适配器。

    未安装 LightRAG 时返回空结果（不影响主流程）。
    """

    def __init__(self) -> None:
        self._rag = None
        self._ready = self._init()

    def _init(self) -> bool:
        try:
            import os

            from lightrag import LightRAG
            from lightrag.utils import EmbeddingFunc

            self._rag = LightRAG(
                working_dir=os.environ.get("XAGENT_KNOWLEDGE_DIR")
                or str(data_path("knowledge")),
                embedding=EmbeddingFunc(
                    model="text-embedding-3-small",
                    api_key=os.environ.get("XAGENT_LLM__OPENAI_API_KEY", ""),
                ),
            )
            logger.info("knowledge_ready")
            return True
        except Exception as exc:
            logger.info("knowledge_not_available", detail=str(exc))
            return False

    @property
    def available(self) -> bool:
        return self._ready

    async def insert(self, text: str) -> None:
        rag = self._rag
        if not self._ready or rag is None:
            return
        rag.insert(text)

    async def query(self, text: str, mode: str = "hybrid") -> str:
        rag = self._rag
        if not self._ready or rag is None:
            return ""
        try:
            return rag.query(text, mode=mode)
        except Exception as exc:
            logger.warning("knowledge_query_failed", error=str(exc))
            return ""


@lru_cache
def get_knowledge() -> KnowledgeRetriever:
    return KnowledgeRetriever()


def reset_knowledge() -> None:
    get_knowledge.cache_clear()
