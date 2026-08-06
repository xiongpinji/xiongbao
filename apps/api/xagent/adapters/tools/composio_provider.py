"""Composio 工具后端适配：1000+ SaaS 工具 + OAuth 认证管理。

把 Composio 工具注册到 X-Agent 的 ToolRegistry，agent 可通过
function-calling 调用外部服务（Google/GitHub/Slack/Notion 等）。
内置 OAuth 认证管理，解决 agent 调用第三方 API 的认证难题。
"""

from __future__ import annotations

from typing import Any

from xagent.adapters.tools.base import Tool, ToolContext, ToolResult, ToolSpec
from xagent.infra.logging import get_logger

logger = get_logger("xagent.composio")


class ComposioTool(Tool):
    """把单个 Composio 动作包装为 X-Agent Tool。"""

    def __init__(
        self, action_name: str, description: str, parameters: dict[str, Any]
    ) -> None:
        self._name = action_name
        self._description = description
        self._parameters = parameters
        self.spec = ToolSpec(
            name=f"composio_{action_name}",
            description=description,
            parameters=parameters,
        )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            from composio import ComposioToolSet

            toolset = ComposioToolSet()
            result = toolset.execute_action(self._name, args)
            return ToolResult(ok=True, output=result)
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))


def get_composio_tools() -> list[Tool]:
    """获取 Composio 工具列表，按需注册进 ToolRegistry。

    Composio SDK 通过 ComposioToolSet 动态获取已授权的动作列表。
    需先运行 ``composio add <app>`` 授权应用（如 GitHub/Slack 等）。
    """
    try:
        from composio import ComposioToolSet

        toolset = ComposioToolSet()
        actions = toolset.get_actions()
        tools: list[Tool] = [
            ComposioTool(
                action_name=a.get("name", ""),
                description=a.get("description", ""),
                parameters=a.get("parameters", {}),
            )
            for a in actions
            if a.get("enabled", False)
        ]
        logger.info("composio_tools_loaded", count=len(tools))
        return tools
    except Exception as exc:
        logger.warning("composio_load_failed", error=str(exc))
        return []
