"""插件内核（单一实现，取代旧仓 16 个 plugin_* 重复版本）。

职责：注册/列举/启停/调用插件。插件 = 一组 Tool 的命名包。
工具后端可来自内置、MCP（adapters/mcp）或 Composio（Phase 3 接入点）。
"""

from xagent.adapters.plugins.kernel import (
    Plugin,
    PluginManager,
    get_plugin_manager,
    reset_plugin_manager,
)

__all__ = ["Plugin", "PluginManager", "get_plugin_manager", "reset_plugin_manager"]
