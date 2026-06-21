"""工具注册表：注册 / 查找 / 列举工具，喂给 LLM 的 function schema 由此聚合。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from xagent.adapters.tools.base import Tool, ToolContext, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.spec.name] = tool

    def register_many(self, tools: list[Tool]) -> None:
        for t in tools:
            self.register(t)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        """OpenAI function-calling 风格 schema 列表。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.spec.name,
                    "description": t.spec.description,
                    "parameters": t.spec.parameters,
                },
            }
            for t in self._tools.values()
        ]

    async def call(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"未知工具: {name}")
        try:
            return await tool.run(args, ctx)
        except Exception as exc:  # 工具内部异常不应炸穿编排循环
            return ToolResult(ok=False, error=f"工具执行异常: {exc}")


@lru_cache
def get_tool_registry() -> ToolRegistry:
    from xagent.adapters.tools.builtin import builtin_tools

    registry = ToolRegistry()
    registry.register_many(builtin_tools())
    # 注册浏览器工具（stub 降级时也注册，调用会返回明确提示）
    try:
        from xagent.adapters.browser.tools import browser_tools

        registry.register_many(browser_tools())
    except Exception as exc:  # 浏览器适配未就绪时不影响启动
        from xagent.infra.logging import get_logger

        get_logger("xagent.tools").warning("browser_tools_register_failed", error=str(exc))
    # 注册剪辑工具（智能体可操作视频剪辑）
    try:
        from xagent.domains.creative_studio.editor.tools import editor_tools

        registry.register_many(editor_tools())
    except Exception:  # noqa: S110  剪辑工具注册失败不影响启动
        pass
    # 注册 Composio 工具（1000+ SaaS，需先 composio add <app> 授权）
    try:
        from xagent.adapters.tools.composio_provider import get_composio_tools

        registry.register_many(get_composio_tools())
    except Exception:  # noqa: S110  Composio 未授权时不注册
        pass
    return registry


def reset_tool_registry() -> None:
    get_tool_registry.cache_clear()
