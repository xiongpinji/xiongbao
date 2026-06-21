"""嵌入实现：优先用 LiteLLM 嵌入模型，无 key 时降级为确定性哈希嵌入。

哈希嵌入保证离线/CI 下向量链路可端到端跑通（语义不准，但形状/检索机制正确）。
"""

from __future__ import annotations

import hashlib
import math

from xagent.infra.settings import MemorySettings


class LiteLLMEmbedder:
    def __init__(
        self,
        cfg: MemorySettings,
        api_key: str = "",
        proxy_url: str = "",
        proxy_api_key: str = "",
    ) -> None:
        self._cfg = cfg
        self._api_key = api_key
        self._proxy_url = proxy_url
        self._proxy_api_key = proxy_api_key

    @property
    def dim(self) -> int:
        return self._cfg.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import litellm

        kwargs = {"model": self._cfg.embedding_model, "input": texts}
        if self._proxy_url:
            # 走 LiteLLM Proxy（OpenAI 兼容端点）
            kwargs["api_base"] = self._proxy_url
            if self._proxy_api_key:
                kwargs["api_key"] = self._proxy_api_key
        elif self._api_key:
            kwargs["api_key"] = self._api_key
        resp = await litellm.aembedding(**kwargs)
        return [item["embedding"] for item in resp["data"]]


class HashEmbedder:
    """确定性哈希嵌入（离线降级）。同文本必得同向量，已 L2 归一化。"""

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        # 对每个词哈希分桶累加，得到稀疏 bag-of-words 风格向量
        for token in text.lower().split():
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            vec[h % self._dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
