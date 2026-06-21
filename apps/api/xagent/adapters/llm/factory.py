"""LLM 客户端工厂。

选择逻辑：
- 配置了 proxy_url 或任一 provider key  -> LiteLLMClient
- 否则                                  -> MockLLMClient（离线降级）
"""

from __future__ import annotations

from functools import lru_cache

from xagent.adapters.llm.base import LLMClient
from xagent.adapters.llm.litellm_client import LiteLLMClient
from xagent.adapters.llm.mock import MockLLMClient
from xagent.infra.settings import get_settings


@lru_cache
def get_llm_client() -> LLMClient:
    cfg = get_settings().llm
    has_backend = bool(
        cfg.proxy_url
        or cfg.ollama_base_url
        or cfg.openai_api_key
        or cfg.anthropic_api_key
        or cfg.deepseek_api_key
    )
    if has_backend:
        return LiteLLMClient(cfg)
    return MockLLMClient()


def reset_llm_client() -> None:
    get_llm_client.cache_clear()
