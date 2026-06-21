"""工具适配层：统一 Tool 协议 + 注册表 + 内置工具。

agent 编排通过 ToolRegistry 拿到可用工具；工具来源可以是内置、MCP（adapters/mcp）
或 Composio（Phase 3）。所有工具调用都带 Principal，便于租户隔离与审计。
"""

from xagent.adapters.tools.base import Tool, ToolResult, ToolSpec
from xagent.adapters.tools.registry import ToolRegistry, get_tool_registry, reset_tool_registry

__all__ = [
    "Tool",
    "ToolResult",
    "ToolSpec",
    "ToolRegistry",
    "get_tool_registry",
    "reset_tool_registry",
]
