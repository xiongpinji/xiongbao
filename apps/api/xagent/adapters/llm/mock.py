"""Mock LLM：无任何 provider key 时的确定性降级实现。

保证 lite 演示 / 离线测试 / CI 不依赖外网即可走通流程（沿用旧仓 mock 回退思想）。
"""

from __future__ import annotations

from typing import Any

from xagent.adapters.llm.base import LLMClient, LLMResponse, Message


class MockLLMClient(LLMClient):
    supports_tools = False

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        content = f"[mock] 收到 {len(messages)} 条消息；最后一条用户内容：{last_user[:200]}"
        return LLMResponse(
            content=content,
            model=model or "mock",
            prompt_tokens=sum(len(m.content) for m in messages) // 4,
            completion_tokens=len(content) // 4,
        )

    async def complete_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        raise NotImplementedError("MockLLM 不支持原生 function-calling")

    async def health(self) -> bool:
        return True
