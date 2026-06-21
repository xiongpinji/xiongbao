"""MCP 适配层：官方 MCP SDK 客户端 + 工具发现。

未安装 mcp / 未配置 server 时为空实现（lite），不影响启动。发现到的 MCP 工具
会被包装成 adapters.tools.Tool 注册进统一 ToolRegistry。
"""

from xagent.adapters.mcp.client import MCPManager, get_mcp_manager, reset_mcp_manager

__all__ = ["MCPManager", "get_mcp_manager", "reset_mcp_manager"]
