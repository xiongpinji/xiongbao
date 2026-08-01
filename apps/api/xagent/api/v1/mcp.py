"""MCP 通用接口：动态管理 MCP Server + 查看/调用工具。

支持接入任意 MCP 服务器（stdio/sse/streamable_http），
发现的工具自动注册到 Agent 工具集。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from xagent.adapters.mcp import get_mcp_manager
from xagent.adapters.mcp.client import MCPServerConfig
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/mcp", tags=["mcp"])


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
    result = {"status": "added", "name": body.name}
    if body.enabled:
        conn = await mgr.connect_server(body.name)
        result["connection"] = conn
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
    result = await mgr.connect_server(name)
    return result


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
