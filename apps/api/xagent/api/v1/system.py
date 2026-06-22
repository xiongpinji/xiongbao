"""系统能力概览路由：让前端设置页能读取当前可用的工具、MCP、命令等只读信息。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from xagent.adapters.mcp import get_mcp_manager
from xagent.adapters.tools import get_tool_registry
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/capabilities", summary="工作台只读能力概览")
async def capabilities(
    principal: Principal = Depends(require_permission("audit", "read")),
) -> dict:
    tools = get_tool_registry()
    mcp = get_mcp_manager()

    tool_items = []
    for name in tools.names():
        tool = tools.get(name)
        tool_items.append({
            "name": name,
            "description": getattr(tool, "description", ""),
            "kind": getattr(tool, "kind", "function"),
        })

    mcp_servers = [
        {
            "name": getattr(srv, "name", "unknown"),
            "kind": getattr(srv, "transport", "stdio"),
            "endpoint": getattr(srv, "endpoint", "") or getattr(srv, "command", ""),
            "enabled": getattr(srv, "enabled", False),
        }
        for srv in mcp.servers
    ]

    return {
        "tenant": principal.tenant_id,
        "tools": tool_items,
        "mcp_servers": mcp_servers,
        "commands": [
            {"name": "/new", "description": "新建任务"},
            {"name": "/search", "description": "搜索工作区"},
            {"name": "/run-canvas", "description": "执行当前短剧画布"},
            {"name": "/export", "description": "导出当前剪辑节点产物"},
        ],
        "code_preview": {
            "default_theme": "neutral-dark",
            "tab_size": 2,
            "diff_mode": "side-by-side",
        },
        "onboarding": [
            "在工作区新建任务或打开项目",
            "在短剧工厂自由画布右键添加流程节点",
            "运行画布触发真实 WorkflowEngine",
            "在剪辑节点 / 导出节点完成短剧产出",
        ],
    }
