"""Minimal MCP server for testing X-Agent MCP integration (MCP 2.0 API)."""
import asyncio
import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

app = Server("xagent-test")


async def handle_list_tools(ctx, params: types.RequestParams) -> types.ListToolsResult:
    return types.ListToolsResult(
        tools=[
            types.Tool(
                name="hello",
                description="Say hello to someone",
                inputSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Name to greet"}},
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="add_numbers",
                description="Add two numbers together",
                inputSchema={
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                },
            ),
            types.Tool(
                name="get_time",
                description="Get current server time",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]
    )


async def handle_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    name = params.name
    arguments = params.arguments or {}
    if name == "hello":
        who = arguments.get("name", "World")
        text = f"Hello, {who}! From MCP Server."
    elif name == "add_numbers":
        result = arguments.get("a", 0) + arguments.get("b", 0)
        text = f"Result: {result}"
    elif name == "get_time":
        text = f"Server time: {datetime.datetime.now().isoformat()}"
    else:
        text = f"Unknown tool: {name}"
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)])


app.add_request_handler("tools/list", types.RequestParams, handle_list_tools)
app.add_request_handler("tools/call", types.CallToolRequestParams, handle_call_tool)


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
