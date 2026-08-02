"""LiteLLM 实现：统一 100+ provider。

两种工作方式：
- proxy_url 非空：走 LiteLLM Proxy（推荐 full 模式，路由/限流/虚拟 key 在 proxy 侧）。
- proxy_url 为空：进程内直连 litellm.acompletion，provider key 从 settings/环境读取。

支持流式（stream=True）逐 token 输出。
"""

from __future__ import annotations

import json as _json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from xagent.adapters.llm.base import LLMClient, LLMResponse, Message, ToolCall
from xagent.infra.settings import LLMSettings


@dataclass
class StreamChunk:
    """流式输出的单个 chunk。"""
    delta_content: str = ""
    tool_call_deltas: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    # ── 流式 token 用量（最后一个 chunk 携带） ──
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LiteLLMClient(LLMClient):
    supports_tools = True

    def __init__(self, cfg: LLMSettings) -> None:
        self._cfg = cfg

    @property
    def effective_model(self) -> str:
        """实际使用的模型名（带 litellm provider 前缀供路由）。

        - proxy: 始终使用 default_model，由 proxy 侧做最终路由
        - ollama: 加 ollama/ 前缀
        - deepseek 直连（无 proxy/ollama）: 加 deepseek/ 前缀
        - 其他: 原样返回（openai 兼容）
        """
        if self._cfg.proxy_url:
            return self._cfg.default_model
        if self._cfg.ollama_base_url:
            model = self._cfg.ollama_model or self._cfg.default_model
            return model if model.startswith("ollama/") else f"ollama/{model}"
        if self._cfg.deepseek_api_key:
            model = self._cfg.default_model
            return model if model.startswith("deepseek/") else f"deepseek/{model}"
        return self._cfg.default_model

    def _call_kwargs(self, model: str | None = None) -> dict[str, Any]:
        target = model or self.effective_model
        kwargs: dict[str, Any] = {
            "model": target,
            "timeout": self._cfg.request_timeout_seconds,
        }
        if self._cfg.proxy_url:
            # 走 LiteLLM Proxy：以 OpenAI 兼容端点形式调用
            kwargs["api_base"] = self._cfg.proxy_url
            if self._cfg.proxy_api_key:
                kwargs["api_key"] = self._cfg.proxy_api_key
        elif self._cfg.ollama_base_url:
            # 走本地 Ollama：LiteLLM 用 ollama/ 前缀 + api_base 路由
            kwargs["api_base"] = self._cfg.ollama_base_url
        elif self._cfg.deepseek_api_key and target.startswith("deepseek/"):
            # 直连 DeepSeek：litellm 靠 deepseek/ 前缀 + api_key 路由
            kwargs["api_key"] = self._cfg.deepseek_api_key
        elif self._cfg.openai_api_key:
            # 直连 OpenAI 兼容
            kwargs["api_key"] = self._cfg.openai_api_key
        elif self._cfg.anthropic_api_key and target.startswith("anthropic/"):
            kwargs["api_key"] = self._cfg.anthropic_api_key
        return kwargs

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        return await self._complete(
            messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs
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
        return await self._complete(
            messages,
            model=model,
            temperature=temperature,
            tools=tools,
            **kwargs,
        )

    async def _complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        import litellm

        target_model = model or self.effective_model
        payload = self._serialize_messages(messages)
        call_kwargs = self._call_kwargs(target_model)
        call_kwargs.update(temperature=temperature, **kwargs)
        if max_tokens:
            call_kwargs["max_tokens"] = max_tokens
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"

        resp = await litellm.acompletion(messages=payload, **call_kwargs)
        choice = resp["choices"][0]
        msg = choice["message"]
        content = msg.get("content") or ""
        usage = resp.get("usage", {}) or {}
        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            import json as _json

            fn = tc.get("function", {})
            try:
                args = _json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), args=args))
        return LLMResponse(
            content=content,
            model=target_model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            tool_calls=tool_calls,
            raw=dict(resp) if isinstance(resp, dict) else {},
        )

    async def stream_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """流式带工具补全，逐 chunk 产出。"""
        import litellm

        target_model = model or self.effective_model
        payload = self._serialize_messages(messages)
        call_kwargs = self._call_kwargs(target_model)
        call_kwargs.update(temperature=temperature, stream=True, **kwargs)
        call_kwargs["tools"] = tools
        call_kwargs["tool_choice"] = "auto"
        # 请求流式 usage（OpenAI 兼容接口支持）
        call_kwargs["stream_options"] = {"include_usage": True}

        resp = await litellm.acompletion(messages=payload, **call_kwargs)
        async for chunk in resp:
            # 提取 usage（通常在最后一个 chunk）
            _usage = chunk.get("usage") or {}
            choices = chunk.get("choices") or []
            if not choices:
                # 无 choices 但有 usage → 纯 usage chunk
                if _usage:
                    yield StreamChunk(
                        finished=True,
                        prompt_tokens=_usage.get("prompt_tokens", 0),
                        completion_tokens=_usage.get("completion_tokens", 0),
                    )
                continue
            delta = choices[0].get("delta") or {}
            finish = choices[0].get("finish_reason")
            yield StreamChunk(
                delta_content=delta.get("content") or "",
                tool_call_deltas=delta.get("tool_calls") or [],
                finished=finish is not None,
                prompt_tokens=_usage.get("prompt_tokens", 0),
                completion_tokens=_usage.get("completion_tokens", 0),
            )

    async def stream_complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """纯文本流式输出，逐 token yield 字符串。"""
        import litellm

        target_model = model or self.effective_model
        payload = self._serialize_messages(messages)
        call_kwargs = self._call_kwargs(target_model)
        call_kwargs.update(temperature=temperature, stream=True, **kwargs)

        resp = await litellm.acompletion(messages=payload, **call_kwargs)
        async for chunk in resp:
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content") or ""
            if content:
                yield content

    @staticmethod
    def _serialize_messages(messages: list[Message]) -> list[dict[str, Any]]:
        """将 Message 列表序列化为 OpenAI API 格式，支持原生 tool role。"""
        payload: list[dict[str, Any]] = []
        for m in messages:
            entry: dict[str, Any] = {"role": m.role, "content": m.content or ""}
            if m.role == "tool":
                entry["tool_call_id"] = m.tool_call_id or ""
                if m.name:
                    entry["name"] = m.name
            payload.append(entry)
        return payload

    async def health(self) -> bool:
        # proxy / ollama / 任意直连 key 任一可用
        return bool(
            self._cfg.proxy_url
            or self._cfg.ollama_base_url
            or self._cfg.openai_api_key
            or self._cfg.deepseek_api_key
            or self._cfg.anthropic_api_key
        )
