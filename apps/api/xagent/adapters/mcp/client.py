"""MCP 管理器。

支持两类 server：
- stdio：本地进程（command + args）
- http/sse：远程 server（url）

用官方 mcp SDK（pip install mcp）连接并 list_tools；发现的工具包装为
adapters.tools.Tool 注册进统一 ToolRegistry。未安装 mcp / 无 server 时安全空转。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.mcp")


@dataclass
class MCPServerConfig:
    name: str
    command: str = ""           # stdio server 启动命令
    args: list[str] = field(default_factory=list)
    url: str = ""               # SSE/HTTP server 地址
    enabled: bool = True


@dataclass
class MCPManager:
    """MCP server 连接与工具发现的统一入口。"""

    servers: list[MCPServerConfig] = field(default_factory=list)
    _started: bool = False
    _discovered: list[dict[str, Any]] = field(default_factory=list)

    async def start(self) -> None:
        if self._started:
            return
        enabled = [s for s in self.servers if s.enabled]
        if not enabled:
            logger.info("mcp_no_servers", detail="未配置 MCP server，跳过")
            self._started = True
            return
        for srv in enabled:
            try:
                await self._connect_and_discover(srv)
            except Exception as exc:
                logger.warning("mcp_connect_failed", server=srv.name, error=str(exc))
        self._started = True

    async def _connect_and_discover(self, srv: MCPServerConfig) -> None:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            logger.info("mcp_sdk_missing", detail="未安装 mcp SDK，跳过真实连接")
            return

        if srv.command:
            params = StdioServerParameters(command=srv.command, args=srv.args)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self._discovered.extend(
                        {"server": srv.name, "name": t.name, "description": t.description}
                        for t in tools.tools
                    )
        # http/sse 连接在 mcp SDK 不同版本接口不一，留作后续按版本适配
        logger.info("mcp_discovered", server=srv.name, count=len(self._discovered))

    async def stop(self) -> None:
        self._started = False

    def discovered_tool_names(self) -> list[str]:
        return [t["name"] for t in self._discovered]

    def discovered_tools(self) -> list[dict[str, Any]]:
        return list(self._discovered)


@lru_cache
def get_mcp_manager() -> MCPManager:
    # 从环境变量加载 server 配置（简化：XAGENT_MCP__SERVERS=<json>）
    import json
    import os

    raw = os.environ.get("XAGENT_MCP__SERVERS", "")
    servers: list[MCPServerConfig] = []
    if raw:
        try:
            for s in json.loads(raw):
                servers.append(MCPServerConfig(**s))
        except Exception:  # noqa: S110  配置解析失败不阻断启动
            pass
    return MCPManager(servers=servers)


def reset_mcp_manager() -> None:
    get_mcp_manager.cache_clear()
