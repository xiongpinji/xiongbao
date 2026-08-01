"""Huobao Drama MCP Server — 将短剧平台 API 包装为 MCP 工具。

X-Agent 通过 MCP 协议调用短剧全流程能力：
创建短剧 → 管理剧集 → 角色/场景 → 分镜 → AI生成 → 合成导出
"""
import asyncio
import json
import os

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

BASE_URL = os.environ.get("HUOBAO_BASE_URL", "http://localhost:5679/api/v1")

app = Server("huobao-drama")


async def _api(method: str, path: str, body: dict | None = None) -> dict:
    """Call huobao-drama REST API."""
    url = f"{BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        if method == "GET":
            resp = await client.get(url)
        elif method == "POST":
            resp = await client.post(url, json=body or {})
        elif method == "PUT":
            resp = await client.put(url, json=body or {})
        elif method == "DELETE":
            resp = await client.delete(url)
        else:
            return {"error": f"Unsupported method: {method}"}
        return resp.json()


# ─── Tool Definitions ───

TOOLS = [
    types.Tool(
        name="list_dramas",
        description="列出所有短剧项目",
        inputSchema={"type": "object", "properties": {"page": {"type": "integer", "description": "页码"}, "keyword": {"type": "string", "description": "搜索关键词"}}, "required": []},
    ),
    types.Tool(
        name="create_drama",
        description="创建新短剧项目",
        inputSchema={"type": "object", "properties": {"title": {"type": "string", "description": "短剧标题"}, "description": {"type": "string", "description": "简介"}, "genre": {"type": "string", "description": "类型(都市/玄幻/悬疑等)"}, "style": {"type": "string", "description": "风格"}}, "required": ["title"]},
    ),
    types.Tool(
        name="get_drama",
        description="获取短剧详情(含剧集/角色/场景)",
        inputSchema={"type": "object", "properties": {"drama_id": {"type": "integer", "description": "短剧ID"}}, "required": ["drama_id"]},
    ),
    types.Tool(
        name="create_episode",
        description="为短剧创建新剧集",
        inputSchema={"type": "object", "properties": {"drama_id": {"type": "integer", "description": "短剧ID"}, "title": {"type": "string", "description": "剧集标题"}, "episode_number": {"type": "integer", "description": "集号"}}, "required": ["drama_id", "title"]},
    ),
    types.Tool(
        name="create_character",
        description="创建角色",
        inputSchema={"type": "object", "properties": {"drama_id": {"type": "integer", "description": "短剧ID"}, "name": {"type": "string", "description": "角色名"}, "description": {"type": "string", "description": "角色描述"}, "personality": {"type": "string", "description": "性格"}}, "required": ["drama_id", "name"]},
    ),
    types.Tool(
        name="create_scene",
        description="创建场景",
        inputSchema={"type": "object", "properties": {"drama_id": {"type": "integer", "description": "短剧ID"}, "name": {"type": "string", "description": "场景名"}, "description": {"type": "string", "description": "场景描述"}}, "required": ["drama_id", "name"]},
    ),
    types.Tool(
        name="create_storyboard",
        description="创建分镜",
        inputSchema={"type": "object", "properties": {"episode_id": {"type": "integer", "description": "剧集ID"}, "scene_description": {"type": "string", "description": "画面描述"}, "dialogue": {"type": "string", "description": "台词"}, "camera_angle": {"type": "string", "description": "镜头角度"}}, "required": ["episode_id", "scene_description"]},
    ),
    types.Tool(
        name="agent_chat",
        description="调用短剧AI Agent(剧本改写/角色提取/分镜拆解/配音分配/提示词生成)",
        inputSchema={"type": "object", "properties": {"agent_type": {"type": "string", "enum": ["script_rewriter", "extractor", "storyboard_breaker", "voice_assigner", "grid_prompt_generator"], "description": "Agent类型"}, "message": {"type": "string", "description": "输入内容"}, "drama_id": {"type": "integer", "description": "短剧ID"}, "episode_id": {"type": "integer", "description": "剧集ID"}}, "required": ["agent_type", "message", "drama_id", "episode_id"]},
    ),
    types.Tool(
        name="get_pipeline_status",
        description="获取剧集生产流水线状态",
        inputSchema={"type": "object", "properties": {"episode_id": {"type": "integer", "description": "剧集ID"}}, "required": ["episode_id"]},
    ),
]


async def handle_list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def handle_call_tool(ctx, params) -> types.CallToolResult:
    name = params.name
    args = params.arguments or {}
    try:
        result = await _dispatch(name, args)
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))])
    except Exception as e:
        return types.CallToolResult(content=[types.TextContent(type="text", text=f"ERROR: {type(e).__name__}: {e}")], isError=True)


async def _dispatch(name: str, args: dict) -> dict:
    if name == "list_dramas":
        params = "?"
        if args.get("page"):
            params += f"page={args['page']}&"
        if args.get("keyword"):
            params += f"keyword={args['keyword']}&"
        return await _api("GET", f"/dramas{params.rstrip('?&')}")
    elif name == "create_drama":
        return await _api("POST", "/dramas", {"title": args["title"], "description": args.get("description", ""), "genre": args.get("genre", ""), "style": args.get("style", "")})
    elif name == "get_drama":
        return await _api("GET", f"/dramas/{args['drama_id']}")
    elif name == "create_episode":
        return await _api("POST", "/episodes", {"drama_id": args["drama_id"], "title": args["title"], "episode_number": args.get("episode_number", 1)})
    elif name == "create_character":
        return await _api("PUT", f"/dramas/{args['drama_id']}/characters", {"characters": [{"name": args["name"], "description": args.get("description", ""), "personality": args.get("personality", "")}]})
    elif name == "create_scene":
        return await _api("POST", "/scenes", {"drama_id": args["drama_id"], "name": args["name"], "description": args.get("description", "")})
    elif name == "create_storyboard":
        return await _api("POST", "/storyboards", {"episode_id": args["episode_id"], "scene_description": args["scene_description"], "dialogue": args.get("dialogue", ""), "camera_angle": args.get("camera_angle", "")})
    elif name == "agent_chat":
        return await _api("POST", f"/agent/{args['agent_type']}/chat", {"message": args["message"], "drama_id": args["drama_id"], "episode_id": args["episode_id"]})
    elif name == "get_pipeline_status":
        return await _api("GET", f"/episodes/{args['episode_id']}/pipeline-status")
    else:
        return {"error": f"Unknown tool: {name}"}


app.add_request_handler("tools/list", types.RequestParams, handle_list_tools)
app.add_request_handler("tools/call", types.CallToolRequestParams, handle_call_tool)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
