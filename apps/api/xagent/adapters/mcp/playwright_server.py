"""Playwright MCP Server — 浏览器自动化工具。

通过 Playwright 提供无头浏览器操作：
- 导航到 URL
- 截图（全页/元素）
- 点击/填写/选择
- 执行 JavaScript
- 获取页面内容/DOM 快照
- 等待元素/导航

需要: pip install playwright && playwright install chromium
"""
import asyncio
import base64
import json
import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

app = Server("xagent-playwright")

# 全局浏览器实例（懒加载）
_browser = None
_page = None
_playwright = None


async def _ensure_browser():
    """Lazily start browser."""
    global _browser, _page, _playwright
    if _page is not None:
        return _page
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("playwright not installed. Run: pip install playwright && playwright install chromium")
    _playwright = await async_playwright().start()
    headless = os.environ.get("PW_HEADLESS", "true").lower() != "false"
    _browser = await _playwright.chromium.launch(headless=headless)
    _page = await _browser.new_page(viewport={"width": 1280, "height": 720})
    return _page


async def _cleanup():
    global _browser, _page, _playwright
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()
    _browser = _page = _playwright = None


# ─── Tool Definitions ───

TOOLS = [
    types.Tool(
        name="navigate",
        description="导航到指定 URL",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标URL"},
                "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle"], "description": "等待条件(默认load)"},
                "timeout": {"type": "integer", "description": "超时毫秒(默认30000)"},
            },
            "required": ["url"],
        },
    ),
    types.Tool(
        name="screenshot",
        description="截取当前页面截图（返回 base64 PNG）",
        inputSchema={
            "type": "object",
            "properties": {
                "full_page": {"type": "boolean", "description": "是否全页截图(默认false)"},
                "selector": {"type": "string", "description": "元素选择器(截取特定元素)"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="click",
        description="点击页面元素",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS/XPath 选择器"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "鼠标按键(默认left)"},
                "click_count": {"type": "integer", "description": "点击次数(默认1)"},
            },
            "required": ["selector"],
        },
    ),
    types.Tool(
        name="fill",
        description="填写输入框",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS/XPath 选择器"},
                "value": {"type": "string", "description": "填入的值"},
            },
            "required": ["selector", "value"],
        },
    ),
    types.Tool(
        name="select_option",
        description="选择下拉框选项",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "select 元素选择器"},
                "value": {"type": "string", "description": "选项值"},
            },
            "required": ["selector", "value"],
        },
    ),
    types.Tool(
        name="evaluate",
        description="在页面中执行 JavaScript 并返回结果",
        inputSchema={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "JavaScript 表达式"},
            },
            "required": ["expression"],
        },
    ),
    types.Tool(
        name="get_content",
        description="获取当前页面 HTML 内容",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "元素选择器(默认body)"},
                "outer": {"type": "boolean", "description": "是否包含元素自身(默认true)"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_text",
        description="获取页面/元素的纯文本内容",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "元素选择器(默认body)"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="wait_for_selector",
        description="等待元素出现",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS/XPath 选择器"},
                "state": {"type": "string", "enum": ["visible", "hidden", "attached"], "description": "等待状态(默认visible)"},
                "timeout": {"type": "integer", "description": "超时毫秒(默认30000)"},
            },
            "required": ["selector"],
        },
    ),
    types.Tool(
        name="get_url",
        description="获取当前页面 URL 和标题",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="go_back",
        description="浏览器后退",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="new_tab",
        description="打开新标签页并导航",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标URL"},
            },
            "required": ["url"],
        },
    ),
    types.Tool(
        name="close_browser",
        description="关闭浏览器实例",
        inputSchema={"type": "object", "properties": {}},
    ),
]


async def handle_list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def handle_call_tool(ctx, params) -> types.CallToolResult:
    name = params.name
    args = params.arguments or {}
    try:
        result = await _dispatch(name, args)
        if isinstance(result, dict) and result.get("_screenshot"):
            # 截图返回 base64
            return types.CallToolResult(content=[
                types.TextContent(type="text", text=f"Screenshot captured ({result.get('size', '?')} bytes). Base64 PNG:"),
                types.TextContent(type="text", text=result["base64"][:50000]),
            ])
        text = json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result)
        if len(text) > 10000:
            text = text[:10000] + "\n... (truncated)"
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)])
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"ERROR: {type(e).__name__}: {e}")], isError=True
        )


async def _dispatch(name: str, args: dict) -> Any:
    global _page

    if name == "close_browser":
        await _cleanup()
        return {"ok": True, "message": "Browser closed"}

    page = await _ensure_browser()

    if name == "navigate":
        url = args["url"]
        wait_until = args.get("wait_until", "load")
        timeout = args.get("timeout", 30000)
        await page.goto(url, wait_until=wait_until, timeout=timeout)
        return {"ok": True, "url": page.url, "title": await page.title()}

    elif name == "screenshot":
        full_page = args.get("full_page", False)
        selector = args.get("selector", "")
        if selector:
            el = page.locator(selector)
            buf = await el.screenshot()
        else:
            buf = await page.screenshot(full_page=full_page)
        b64 = base64.b64encode(buf).decode()
        return {"_screenshot": True, "base64": b64, "size": len(buf)}

    elif name == "click":
        selector = args["selector"]
        button = args.get("button", "left")
        click_count = args.get("click_count", 1)
        await page.click(selector, button=button, click_count=click_count)
        return {"ok": True, "clicked": selector}

    elif name == "fill":
        await page.fill(args["selector"], args["value"])
        return {"ok": True, "filled": args["selector"]}

    elif name == "select_option":
        await page.select_option(args["selector"], args["value"])
        return {"ok": True, "selected": args["value"]}

    elif name == "evaluate":
        result = await page.evaluate(args["expression"])
        return {"result": result}

    elif name == "get_content":
        selector = args.get("selector", "body")
        outer = args.get("outer", True)
        el = page.locator(selector)
        if outer:
            html = await el.evaluate("el => el.outerHTML")
        else:
            html = await el.inner_html()
        if len(html) > 20000:
            html = html[:20000] + "...(truncated)"
        return {"html": html}

    elif name == "get_text":
        selector = args.get("selector", "body")
        text = await page.inner_text(selector)
        if len(text) > 10000:
            text = text[:10000] + "...(truncated)"
        return {"text": text}

    elif name == "wait_for_selector":
        selector = args["selector"]
        state = args.get("state", "visible")
        timeout = args.get("timeout", 30000)
        await page.wait_for_selector(selector, state=state, timeout=timeout)
        return {"ok": True, "selector": selector, "state": state}

    elif name == "get_url":
        return {"url": page.url, "title": await page.title()}

    elif name == "go_back":
        await page.go_back()
        return {"ok": True, "url": page.url}

    elif name == "new_tab":
        global _browser
        context = page.context
        new_page = await context.new_page()
        await new_page.goto(args["url"])
        _page = new_page
        return {"ok": True, "url": new_page.url, "title": await new_page.title()}

    return {"error": f"Unknown tool: {name}"}


app.add_request_handler("tools/list", types.RequestParams, handle_list_tools)
app.add_request_handler("tools/call", types.CallToolRequestParams, handle_call_tool)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
