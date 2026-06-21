"""浏览器工具：把 BrowserAgent 暴露为 ToolRegistry 里的工具。"""

from __future__ import annotations

from typing import Any

from xagent.adapters.browser import get_browser_agent
from xagent.adapters.tools.base import Tool, ToolContext, ToolResult, ToolSpec


class BrowserRunTool:
    spec = ToolSpec(
        name="browser_run",
        description="用 LLM 驱动浏览器完成一个网页任务（需启用 browser-use）。",
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "浏览器任务描述"},
                "max_steps": {"type": "integer", "default": 15},
            },
            "required": ["task"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        agent = get_browser_agent()
        res = await agent.run(args.get("task", ""), max_steps=int(args.get("max_steps", 15)))
        if res.ok:
            return ToolResult(ok=True, output=res.summary)
        return ToolResult(ok=False, error=res.error)


def browser_tools() -> list[Tool]:
    return [BrowserRunTool()]
