"""LLM 适配层抽象：统一聊天补全接口，屏蔽 LiteLLM / 直连 / mock 差异。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Message:
    role: str  # system | user | assistant | tool
    content: str


@dataclass
class ToolCall:
    """LLM 原生 function-calling 返回的工具调用。"""

    id: str
    name: str
    args: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMClient(Protocol):
    """LLM 客户端抽象。"""

    supports_tools: bool

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """一次性聊天补全。"""
        ...

    async def complete_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """带工具的聊天补全（原生 function-calling）。不支持时抛 NotImplementedError。"""
        ...

    async def health(self) -> bool:
        """探活。"""
        ...
