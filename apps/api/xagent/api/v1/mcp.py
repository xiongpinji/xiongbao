"""MCP 通用接口：动态管理 MCP Server + 查看/调用工具。

支持接入任意 MCP 服务器（stdio/sse/streamable_http），
发现的工具自动注册到 Agent 工具集。
"""

from __future__ import annotations

import shutil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from xagent.adapters.mcp import get_mcp_manager
from xagent.adapters.mcp.client import MCPServerConfig
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _validate_server_config(body: MCPServerIn) -> None:
    """显式校验服务器配置，拒绝必然失败的假成功。"""
    if body.transport == "stdio":
        if not body.command:
            raise HTTPException(400, "stdio 传输必须提供 command")
        # 命令必须真实存在（PATH 或有效路径），否则连接必然失败
        if not shutil.which(body.command):
            raise HTTPException(400, f"stdio 命令不存在或不可执行: '{body.command}'")
    elif body.transport in ("sse", "streamable_http"):
        if not body.url:
            raise HTTPException(400, f"{body.transport} 传输必须提供 url")
    else:
        raise HTTPException(400, f"不支持的 transport: '{body.transport}'")


def _server_view(mgr, name: str) -> dict:
    """获取单个 server 的列表视图（含 connected / tools_count）。"""
    for srv in mgr.list_servers():
        if srv["name"] == name:
            return srv
    return {}


def _honest_connection(mgr, name: str, conn: dict) -> dict:
    """把 manager 的连接结果修正为与事实一致：

    manager 内部会吞掉 stdio/sse 连接异常并返回 ok=True + tools_discovered=0，
    这里用 connected 标志与工具总数校验，失败则明确报错，并补充 tools_count
    （与 GET /mcp/servers 的 tools_count 口径一致，避免"重连后 0 vs 3"矛盾）。
    """
    view = _server_view(mgr, name)
    conn["tools_count"] = len([
        t for t in mgr.discovered_tools() if t["server"] == name
    ])
    if conn.get("ok") and not view.get("connected", False):
        conn["ok"] = False
        conn["error"] = "连接失败：无法建立会话或发现工具（详见服务端日志）"
    return conn


# ─── Server 管理 ───


class MCPServerIn(BaseModel):
    name: str = Field(..., min_length=1, description="服务器唯一名称")
    transport: str = Field(default="stdio", description="stdio | sse | streamable_http")
    command: str = Field(default="", description="stdio 启动命令")
    args: list[str] = Field(default_factory=list, description="stdio 命令参数")
    env: dict[str, str] = Field(default_factory=dict, description="额外环境变量")
    url: str = Field(default="", description="sse/http 服务地址")
    enabled: bool = True


@router.get("/servers", summary="列出所有 MCP Server")
async def list_servers(
    principal: Principal = Depends(require_permission("system", "read")),
):
    mgr = get_mcp_manager()
    return {"servers": mgr.list_servers()}


@router.post("/servers", summary="添加/更新 MCP Server")
async def add_server(
    body: MCPServerIn,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    _validate_server_config(body)
    mgr = get_mcp_manager()
    cfg = MCPServerConfig(
        name=body.name,
        transport=body.transport,
        command=body.command,
        args=body.args,
        env=body.env,
        url=body.url,
        enabled=body.enabled,
    )
    mgr.add_server(cfg)
    # 如果 enabled，立即尝试连接
    result: dict[str, Any] = {"status": "added", "name": body.name}
    if body.enabled:
        conn = await mgr.connect_server(body.name)
        result["connection"] = _honest_connection(mgr, body.name, conn)
    return result


@router.delete("/servers/{name}", summary="移除 MCP Server")
async def remove_server(
    name: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    mgr = get_mcp_manager()
    deleted = mgr.remove_server(name)
    return {"deleted": deleted, "name": name}


@router.post("/servers/{name}/connect", summary="连接指定 Server")
async def connect_server(
    name: str,
    principal: Principal = Depends(require_permission("system", "manage")),
):
    mgr = get_mcp_manager()
    if name not in mgr.servers:
        raise HTTPException(404, f"server '{name}' 不存在")
    result = await mgr.connect_server(name)
    return _honest_connection(mgr, name, result)


# ─── 工具查询 ───


@router.get("/tools", summary="列出所有 MCP 发现的工具")
async def list_tools(
    principal: Principal = Depends(require_permission("system", "read")),
):
    mgr = get_mcp_manager()
    return {"tools": mgr.discovered_tools()}


# ─── 工具调用 ───


class MCPToolCallIn(BaseModel):
    server: str = Field(..., description="服务器名称")
    tool: str = Field(..., description="工具原始名称")
    arguments: dict = Field(default_factory=dict, description="工具参数")


@router.post("/tools/call", summary="调用 MCP 工具")
async def call_tool(
    body: MCPToolCallIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
):
    mgr = get_mcp_manager()
    result = await mgr.call_tool(body.server, body.tool, body.arguments)
    return result
