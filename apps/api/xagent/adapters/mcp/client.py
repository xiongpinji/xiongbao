"""MCP 通用管理器。

支持任意 MCP server 的动态接入：
- stdio：本地进程（command + args）
- sse：远程 SSE server（url）
- streamable_http：新版 MCP HTTP 流式传输

发现的工具自动包装为 adapters.tools.Tool 注册进统一 ToolRegistry，
Agent 可直接调用。支持运行时动态添加/移除 server。
配置持久化到 data/mcp_servers.json。
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.mcp")

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _PROJECT_ROOT / "data" / "mcp_servers.json"


@dataclass
class MCPServerConfig:
    name: str
    transport: str = "stdio"    # stdio | sse | streamable_http
    command: str = ""           # stdio: 启动命令
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)  # 额外环境变量
    url: str = ""               # sse/http: 服务地址
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MCPToolInfo:
    """MCP 发现的工具元数据。"""
    server_name: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


class MCPManager:
    """MCP server 连接、工具发现、动态注册的统一入口。"""

    def __init__(self) -> None:
        self.servers: dict[str, MCPServerConfig] = {}
        self._tools: dict[str, MCPToolInfo] = {}  # tool_name -> info
        self._sessions: dict[str, Any] = {}  # server_name -> active session
        self._started = False
        self._load_config()

    # ─── 配置持久化 ───

    def _load_config(self) -> None:
        """Load server configs from persistent file + env var."""
        # 从文件加载
        if _CONFIG_PATH.is_file():
            try:
                data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                for item in data:
                    cfg = MCPServerConfig(**{k: v for k, v in item.items()})
                    self.servers[cfg.name] = cfg
            except Exception as e:
                logger.warning("mcp_config_load_failed", error=str(e))
        # 从环境变量加载（兼容旧配置）
        raw = os.environ.get("XAGENT_MCP__SERVERS", "")
        if raw:
            try:
                for s in json.loads(raw):
                    cfg = MCPServerConfig(**s)
                    self.servers[cfg.name] = cfg
            except Exception:
                pass

    def _save_config(self) -> None:
        """Persist server configs to file."""
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = [cfg.to_dict() for cfg in self.servers.values()]
        _CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ─── Server 管理 ───

    def add_server(self, config: MCPServerConfig) -> None:
        """Add or update a server config."""
        self.servers[config.name] = config
        self._save_config()
        logger.info("mcp_server_added", name=config.name, transport=config.transport)

    def remove_server(self, name: str) -> bool:
        """Remove a server and its tools."""
        if name not in self.servers:
            return False
        del self.servers[name]
        # 移除该 server 的工具
        self._tools = {k: v for k, v in self._tools.items() if v.server_name != name}
        self._sessions.pop(name, None)
        self._save_config()
        logger.info("mcp_server_removed", name=name)
        return True

    def list_servers(self) -> list[dict[str, Any]]:
        result = []
        for cfg in self.servers.values():
            tools = [t for t in self._tools.values() if t.server_name == cfg.name]
            result.append({
                **cfg.to_dict(),
                "connected": cfg.name in self._sessions,
                "tools_count": len(tools),
            })
        return result

    # ─── 连接与发现 ───

    async def start(self) -> None:
        """Connect to all enabled servers and discover tools."""
        if self._started:
            return
        enabled = [s for s in self.servers.values() if s.enabled]
        if not enabled:
            logger.info("mcp_no_servers", detail="No MCP servers configured")
            self._started = True
            return
        for srv in enabled:
            try:
                await self._connect_and_discover(srv)
            except Exception as exc:
                logger.warning("mcp_connect_failed", server=srv.name, error=str(exc))
        self._started = True
        logger.info("mcp_started", servers=len(enabled), tools=len(self._tools))

    async def connect_server(self, name: str) -> dict[str, Any]:
        """Connect to a specific server (runtime dynamic)."""
        cfg = self.servers.get(name)
        if not cfg:
            return {"ok": False, "error": f"server '{name}' not found"}
        try:
            count = await self._connect_and_discover(cfg)
            return {"ok": True, "tools_discovered": count}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _connect_and_discover(self, srv: MCPServerConfig) -> int:
        """Connect to server, discover tools, return count."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            logger.info("mcp_sdk_missing", detail="pip install mcp to enable")
            return 0

        count_before = len(self._tools)

        if srv.transport == "stdio" and srv.command:
            env = {**os.environ, **srv.env}
            params = StdioServerParameters(
                command=srv.command, args=srv.args, env=env
            )
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        for t in tools_result.tools:
                            tool_name = f"mcp_{srv.name}_{t.name}"
                            self._tools[tool_name] = MCPToolInfo(
                                server_name=srv.name,
                                name=t.name,
                                description=t.description or "",
                                input_schema=getattr(t, "inputSchema", {}) or {},
                            )
                        self._sessions[srv.name] = True  # mark as connected
            except Exception as e:
                logger.warning("mcp_stdio_failed", server=srv.name, error=str(e))

        elif srv.transport in ("sse", "streamable_http") and srv.url:
            # SSE/HTTP 连接（兼容不同版本 mcp SDK）
            try:
                from mcp.client.sse import sse_client
                async with sse_client(srv.url) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        for t in tools_result.tools:
                            tool_name = f"mcp_{srv.name}_{t.name}"
                            self._tools[tool_name] = MCPToolInfo(
                                server_name=srv.name,
                                name=t.name,
                                description=t.description or "",
                                input_schema=getattr(t, "inputSchema", {}) or {},
                            )
                        self._sessions[srv.name] = True
            except ImportError:
                logger.info("mcp_sse_missing", detail="mcp SDK too old for SSE")
            except Exception as e:
                logger.warning("mcp_sse_failed", server=srv.name, error=str(e))

        discovered = len(self._tools) - count_before
        if discovered > 0:
            logger.info("mcp_discovered", server=srv.name, count=discovered)
            # 动态注册到 ToolRegistry
            self._register_tools_to_registry(srv.name)
        return discovered

    def _register_tools_to_registry(self, server_name: str) -> None:
        """Wrap discovered MCP tools as Tool instances and register."""
        try:
            from xagent.adapters.tools.registry import get_tool_registry
            registry = get_tool_registry()
            for tool_name, info in self._tools.items():
                if info.server_name != server_name:
                    continue
                if registry.get(tool_name):
                    continue  # already registered
                # 创建包装工具
                wrapper = _MCPToolWrapper(info, self)
                registry.register(wrapper)
        except Exception as e:
            logger.warning("mcp_register_failed", server=server_name, error=str(e))

    # ─── 工具调用 ───

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Call a tool on a specific MCP server."""
        cfg = self.servers.get(server_name)
        if not cfg:
            return {"error": f"server '{server_name}' not found"}

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            return {"error": "mcp SDK not installed"}

        if cfg.transport == "stdio" and cfg.command:
            env = {**os.environ, **cfg.env}
            params = StdioServerParameters(command=cfg.command, args=cfg.args, env=env)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    # 提取文本内容
                    contents = []
                    for c in (result.content or []):
                        if hasattr(c, "text"):
                            contents.append(c.text)
                    return {"ok": True, "output": "\n".join(contents)}

        elif cfg.transport in ("sse", "streamable_http") and cfg.url:
            try:
                from mcp.client.sse import sse_client
                async with sse_client(cfg.url) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
                        contents = []
                        for c in (result.content or []):
                            if hasattr(c, "text"):
                                contents.append(c.text)
                        return {"ok": True, "output": "\n".join(contents)}
            except Exception as e:
                return {"error": str(e)}

        return {"error": f"unsupported transport: {cfg.transport}"}

    # ─── 查询 ───

    def discovered_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "tool_name": k,
                "server": v.server_name,
                "original_name": v.name,
                "description": v.description,
                "input_schema": v.input_schema,
            }
            for k, v in self._tools.items()
        ]

    def discovered_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def stop(self) -> None:
        self._sessions.clear()
        self._started = False


class _MCPToolWrapper:
    """Wraps an MCP discovered tool as a standard Tool for the registry."""

    def __init__(self, info: MCPToolInfo, manager: MCPManager) -> None:
        from xagent.adapters.tools.base import ToolSpec
        self.spec = ToolSpec(
            name=f"mcp_{info.server_name}_{info.name}",
            description=f"[MCP:{info.server_name}] {info.description}"[:500],
            parameters=info.input_schema or {"type": "object", "properties": {}},
        )
        self._info = info
        self._manager = manager

    async def run(self, args: dict[str, Any], ctx: Any) -> Any:
        from xagent.adapters.tools.base import ToolResult
        result = await self._manager.call_tool(
            self._info.server_name, self._info.name, args
        )
        if isinstance(result, dict) and result.get("ok"):
            return ToolResult(ok=True, output=result.get("output", ""))
        elif isinstance(result, dict) and result.get("error"):
            return ToolResult(ok=False, error=result["error"])
        return ToolResult(ok=True, output=str(result))


# ─── 全局单例 ───

_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager


def reset_mcp_manager() -> None:
    global _manager
    _manager = None
