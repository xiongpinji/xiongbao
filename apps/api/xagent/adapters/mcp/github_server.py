"""GitHub MCP Server — GitHub REST API 操作工具。

通过 GitHub REST API v3 提供：
- 仓库管理（列表/搜索/创建）
- Issue 管理（创建/列表/更新/评论）
- Pull Request（创建/列表/合并/评论）
- 代码搜索
- 文件内容读取
- 分支管理

需要环境变量 GITHUB_TOKEN（Personal Access Token）。
"""
import asyncio
import json
import os

import httpx
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

GITHUB_API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

app = Server("xagent-github")


async def _gh(method: str, path: str, body: dict | None = None, params: dict | None = None) -> dict:
    """Call GitHub REST API."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    url = f"{GITHUB_API}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, json=body, params=params)
        if resp.status_code >= 400:
            return {"error": f"GitHub API {resp.status_code}: {resp.text[:500]}"}
        if resp.status_code == 204:
            return {"ok": True, "status": 204}
        return resp.json()


# ─── Tool Definitions ───

TOOLS = [
    types.Tool(
        name="search_repositories",
        description="搜索 GitHub 仓库",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "language": {"type": "string", "description": "编程语言过滤"},
                "sort": {"type": "string", "enum": ["stars", "forks", "updated"], "description": "排序方式"},
                "per_page": {"type": "integer", "description": "每页数量(默认10)"},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_repository",
        description="获取仓库详情",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
            },
            "required": ["owner", "repo"],
        },
    ),
    types.Tool(
        name="list_issues",
        description="列出仓库 Issues",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
                "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "状态(默认open)"},
                "labels": {"type": "string", "description": "标签过滤(逗号分隔)"},
                "per_page": {"type": "integer", "description": "每页数量(默认10)"},
            },
            "required": ["owner", "repo"],
        },
    ),
    types.Tool(
        name="create_issue",
        description="创建 Issue",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
                "title": {"type": "string", "description": "标题"},
                "body": {"type": "string", "description": "内容(Markdown)"},
                "labels": {"type": "array", "items": {"type": "string"}, "description": "标签列表"},
                "assignees": {"type": "array", "items": {"type": "string"}, "description": "指派人"},
            },
            "required": ["owner", "repo", "title"],
        },
    ),
    types.Tool(
        name="update_issue",
        description="更新 Issue（状态/标题/内容）",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
                "issue_number": {"type": "integer", "description": "Issue编号"},
                "state": {"type": "string", "enum": ["open", "closed"], "description": "新状态"},
                "title": {"type": "string", "description": "新标题"},
                "body": {"type": "string", "description": "新内容"},
            },
            "required": ["owner", "repo", "issue_number"],
        },
    ),
    types.Tool(
        name="add_issue_comment",
        description="为 Issue 添加评论",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
                "issue_number": {"type": "integer", "description": "Issue编号"},
                "body": {"type": "string", "description": "评论内容(Markdown)"},
            },
            "required": ["owner", "repo", "issue_number", "body"],
        },
    ),
    types.Tool(
        name="list_pull_requests",
        description="列出 Pull Requests",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
                "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "状态(默认open)"},
                "per_page": {"type": "integer", "description": "每页数量(默认10)"},
            },
            "required": ["owner", "repo"],
        },
    ),
    types.Tool(
        name="create_pull_request",
        description="创建 Pull Request",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
                "title": {"type": "string", "description": "PR标题"},
                "head": {"type": "string", "description": "源分支"},
                "base": {"type": "string", "description": "目标分支(默认main)"},
                "body": {"type": "string", "description": "PR描述"},
                "draft": {"type": "boolean", "description": "是否为草稿"},
            },
            "required": ["owner", "repo", "title", "head"],
        },
    ),
    types.Tool(
        name="get_file_contents",
        description="获取仓库文件内容",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
                "path": {"type": "string", "description": "文件路径"},
                "ref": {"type": "string", "description": "分支/tag/commit(默认默认分支)"},
            },
            "required": ["owner", "repo", "path"],
        },
    ),
    types.Tool(
        name="search_code",
        description="搜索 GitHub 代码",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词(支持 repo: language: 等限定符)"},
                "per_page": {"type": "integer", "description": "每页数量(默认10)"},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="list_branches",
        description="列出仓库分支",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
                "per_page": {"type": "integer", "description": "每页数量(默认20)"},
            },
            "required": ["owner", "repo"],
        },
    ),
    types.Tool(
        name="create_branch",
        description="创建新分支",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名"},
                "branch": {"type": "string", "description": "新分支名"},
                "from_ref": {"type": "string", "description": "基于的分支/commit(默认main)"},
            },
            "required": ["owner", "repo", "branch"],
        },
    ),
]


async def handle_list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def handle_call_tool(ctx, params) -> types.CallToolResult:
    name = params.name
    args = params.arguments or {}
    try:
        result = await _dispatch(name, args)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        # 截断过长输出
        if len(text) > 8000:
            text = text[:8000] + "\n... (truncated)"
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)])
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"ERROR: {type(e).__name__}: {e}")], isError=True
        )


async def _dispatch(name: str, args: dict) -> dict:
    if name == "search_repositories":
        q = args["query"]
        if args.get("language"):
            q += f" language:{args['language']}"
        params = {"q": q, "per_page": args.get("per_page", 10)}
        if args.get("sort"):
            params["sort"] = args["sort"]
        data = await _gh("GET", "/search/repositories", params=params)
        if "items" in data:
            data["items"] = [
                {"full_name": r["full_name"], "description": r.get("description", ""), "stars": r["stargazers_count"], "language": r.get("language", ""), "url": r["html_url"]}
                for r in data["items"]
            ]
        return data

    elif name == "get_repository":
        return await _gh("GET", f"/repos/{args['owner']}/{args['repo']}")

    elif name == "list_issues":
        params = {"state": args.get("state", "open"), "per_page": args.get("per_page", 10)}
        if args.get("labels"):
            params["labels"] = args["labels"]
        return await _gh("GET", f"/repos/{args['owner']}/{args['repo']}/issues", params=params)

    elif name == "create_issue":
        body = {"title": args["title"]}
        if args.get("body"):
            body["body"] = args["body"]
        if args.get("labels"):
            body["labels"] = args["labels"]
        if args.get("assignees"):
            body["assignees"] = args["assignees"]
        return await _gh("POST", f"/repos/{args['owner']}/{args['repo']}/issues", body=body)

    elif name == "update_issue":
        body = {}
        if args.get("state"):
            body["state"] = args["state"]
        if args.get("title"):
            body["title"] = args["title"]
        if args.get("body"):
            body["body"] = args["body"]
        return await _gh("PATCH", f"/repos/{args['owner']}/{args['repo']}/issues/{args['issue_number']}", body=body)

    elif name == "add_issue_comment":
        return await _gh("POST", f"/repos/{args['owner']}/{args['repo']}/issues/{args['issue_number']}/comments", body={"body": args["body"]})

    elif name == "list_pull_requests":
        params = {"state": args.get("state", "open"), "per_page": args.get("per_page", 10)}
        return await _gh("GET", f"/repos/{args['owner']}/{args['repo']}/pulls", params=params)

    elif name == "create_pull_request":
        body = {
            "title": args["title"],
            "head": args["head"],
            "base": args.get("base", "main"),
        }
        if args.get("body"):
            body["body"] = args["body"]
        if args.get("draft"):
            body["draft"] = True
        return await _gh("POST", f"/repos/{args['owner']}/{args['repo']}/pulls", body=body)

    elif name == "get_file_contents":
        params = {}
        if args.get("ref"):
            params["ref"] = args["ref"]
        data = await _gh("GET", f"/repos/{args['owner']}/{args['repo']}/contents/{args['path']}", params=params)
        # 解码 base64 内容
        if isinstance(data, dict) and data.get("content") and data.get("encoding") == "base64":
            import base64
            try:
                data["decoded_content"] = base64.b64decode(data["content"]).decode("utf-8")
                del data["content"]
            except Exception:
                pass
        return data

    elif name == "search_code":
        params = {"q": args["query"], "per_page": args.get("per_page", 10)}
        data = await _gh("GET", "/search/code", params=params)
        if "items" in data:
            data["items"] = [
                {"name": i["name"], "path": i["path"], "repo": i["repository"]["full_name"], "url": i["html_url"]}
                for i in data["items"]
            ]
        return data

    elif name == "list_branches":
        params = {"per_page": args.get("per_page", 20)}
        return await _gh("GET", f"/repos/{args['owner']}/{args['repo']}/branches", params=params)

    elif name == "create_branch":
        # 先获取 ref
        from_ref = args.get("from_ref", "main")
        ref_data = await _gh("GET", f"/repos/{args['owner']}/{args['repo']}/git/ref/heads/{from_ref}")
        if "error" in ref_data:
            return ref_data
        sha = ref_data["object"]["sha"]
        return await _gh("POST", f"/repos/{args['owner']}/{args['repo']}/git/refs", body={
            "ref": f"refs/heads/{args['branch']}",
            "sha": sha,
        })

    return {"error": f"Unknown tool: {name}"}


app.add_request_handler("tools/list", types.RequestParams, handle_list_tools)
app.add_request_handler("tools/call", types.CallToolRequestParams, handle_call_tool)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
