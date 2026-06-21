"""单一插件内核。

Plugin = metadata + 一组 Tool。PluginManager 管理生命周期（注册/启停/列举）。
调用统一走 ToolRegistry（plugin 的 tool 注册进去即可被编排使用），避免旧仓
plugin_system / plugin_system_v2 / plugin_system_optimized 多版本并存。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from xagent.adapters.tools.base import Tool
from xagent.adapters.tools.registry import get_tool_registry
from xagent.infra.logging import get_logger

logger = get_logger("xagent.plugins")


@dataclass
class Plugin:
    name: str
    version: str
    description: str = ""
    tools: list[Tool] = field(default_factory=list)
    enabled: bool = True


class PluginManager:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        self._plugins[plugin.name] = plugin
        if plugin.enabled:
            self._wire_tools(plugin)
        logger.info("plugin_registered", name=plugin.name, version=plugin.version)

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)

    def enable(self, name: str) -> None:
        p = self._plugins.get(name)
        if p and not p.enabled:
            p.enabled = True
            self._wire_tools(p)

    def disable(self, name: str) -> None:
        p = self._plugins.get(name)
        if p and p.enabled:
            p.enabled = False
            # 注意：工具注册表当前不支持反注册；Phase 5 补 tool namespace 隔离

    def list(self) -> list[dict]:
        return [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "enabled": p.enabled,
                "tools": [t.spec.name for t in p.tools],
            }
            for p in self._plugins.values()
        ]

    def _wire_tools(self, plugin: Plugin) -> None:
        registry = get_tool_registry()
        for tool in plugin.tools:
            registry.register(tool)


@lru_cache
def get_plugin_manager() -> PluginManager:
    return PluginManager()


def reset_plugin_manager() -> None:
    get_plugin_manager.cache_clear()
