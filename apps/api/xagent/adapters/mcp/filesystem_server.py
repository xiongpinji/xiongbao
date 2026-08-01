"""Filesystem MCP Server — 文件系统操作工具。

提供安全的文件/目录操作能力：
- 读取文件内容
- 写入/追加文件
- 列出目录
- 搜索文件（glob/内容）
- 创建目录
- 复制/移动/删除
- 获取文件元信息

安全约束：所有操作限制在 ALLOWED_ROOTS 内（默认 cwd）。
"""
import asyncio
import fnmatch
import json
import os
import shutil
import stat
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# 安全沙箱：允许访问的根目录（环境变量配置，逗号分隔）
_raw_roots = os.environ.get("FS_ALLOWED_ROOTS", ".")
ALLOWED_ROOTS = [Path(r).resolve() for r in _raw_roots.split(",") if r.strip()]

app = Server("xagent-filesystem")


def _safe_path(raw: str) -> Path:
    """Resolve path and ensure it's within allowed roots."""
    p = Path(raw).resolve()
    for root in ALLOWED_ROOTS:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    raise PermissionError(f"Path '{raw}' is outside allowed roots: {[str(r) for r in ALLOWED_ROOTS]}")


def _file_info(p: Path) -> dict:
    """Get file metadata."""
    st = p.stat()
    return {
        "name": p.name,
        "path": str(p),
        "type": "directory" if p.is_dir() else "file",
        "size": st.st_size,
        "modified": st.st_mtime,
        "extension": p.suffix if p.is_file() else "",
    }


# ─── Tool Definitions ───

TOOLS = [
    types.Tool(
        name="read_file",
        description="读取文件内容（支持指定行范围）",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "start_line": {"type": "integer", "description": "起始行(1-based，可选)"},
                "end_line": {"type": "integer", "description": "结束行(可选)"},
                "encoding": {"type": "string", "description": "编码(默认utf-8)"},
            },
            "required": ["path"],
        },
    ),
    types.Tool(
        name="write_file",
        description="写入文件内容（覆盖或追加）",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "写入内容"},
                "mode": {"type": "string", "enum": ["overwrite", "append"], "description": "写入模式(默认overwrite)"},
                "encoding": {"type": "string", "description": "编码(默认utf-8)"},
            },
            "required": ["path", "content"],
        },
    ),
    types.Tool(
        name="list_directory",
        description="列出目录内容（支持递归深度）",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"},
                "recursive": {"type": "boolean", "description": "是否递归(默认false)"},
                "max_depth": {"type": "integer", "description": "最大递归深度(默认3)"},
                "pattern": {"type": "string", "description": "glob过滤(如 *.py)"},
            },
            "required": ["path"],
        },
    ),
    types.Tool(
        name="search_files",
        description="搜索文件（按名称glob或内容关键词）",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "搜索根目录"},
                "name_pattern": {"type": "string", "description": "文件名glob(如 *.ts)"},
                "content_pattern": {"type": "string", "description": "文件内容关键词"},
                "max_results": {"type": "integer", "description": "最大结果数(默认20)"},
            },
            "required": ["path"],
        },
    ),
    types.Tool(
        name="create_directory",
        description="创建目录（含父目录）",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"},
            },
            "required": ["path"],
        },
    ),
    types.Tool(
        name="copy_file",
        description="复制文件或目录",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源路径"},
                "destination": {"type": "string", "description": "目标路径"},
            },
            "required": ["source", "destination"],
        },
    ),
    types.Tool(
        name="move_file",
        description="移动/重命名文件或目录",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源路径"},
                "destination": {"type": "string", "description": "目标路径"},
            },
            "required": ["source", "destination"],
        },
    ),
    types.Tool(
        name="delete_file",
        description="删除文件或空目录",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要删除的路径"},
                "recursive": {"type": "boolean", "description": "目录是否递归删除(默认false)"},
            },
            "required": ["path"],
        },
    ),
    types.Tool(
        name="file_info",
        description="获取文件/目录元信息（大小、修改时间等）",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
            },
            "required": ["path"],
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
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        )
    except PermissionError as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"PERMISSION DENIED: {e}")], isError=True
        )
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"ERROR: {type(e).__name__}: {e}")], isError=True
        )


async def _dispatch(name: str, args: dict) -> dict | list:
    if name == "read_file":
        p = _safe_path(args["path"])
        if not p.is_file():
            return {"error": f"File not found: {args['path']}"}
        encoding = args.get("encoding", "utf-8")
        lines = p.read_text(encoding=encoding).splitlines()
        start = args.get("start_line", 1) - 1
        end = args.get("end_line", len(lines))
        selected = lines[start:end]
        return {
            "path": str(p),
            "total_lines": len(lines),
            "showing": f"{start+1}-{min(end, len(lines))}",
            "content": "\n".join(selected),
        }

    elif name == "write_file":
        p = _safe_path(args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = args.get("mode", "overwrite")
        encoding = args.get("encoding", "utf-8")
        if mode == "append":
            with open(p, "a", encoding=encoding) as f:
                f.write(args["content"])
        else:
            p.write_text(args["content"], encoding=encoding)
        return {"ok": True, "path": str(p), "mode": mode, "size": p.stat().st_size}

    elif name == "list_directory":
        p = _safe_path(args["path"])
        if not p.is_dir():
            return {"error": f"Not a directory: {args['path']}"}
        recursive = args.get("recursive", False)
        max_depth = args.get("max_depth", 3)
        pattern = args.get("pattern", "")
        items = []

        def _walk(d: Path, depth: int):
            if depth > max_depth:
                return
            try:
                for entry in sorted(d.iterdir()):
                    if pattern and entry.is_file() and not fnmatch.fnmatch(entry.name, pattern):
                        continue
                    items.append(_file_info(entry))
                    if recursive and entry.is_dir() and depth < max_depth:
                        _walk(entry, depth + 1)
            except PermissionError:
                pass

        _walk(p, 1)
        return {"path": str(p), "count": len(items), "items": items[:200]}

    elif name == "search_files":
        p = _safe_path(args["path"])
        name_pat = args.get("name_pattern", "")
        content_pat = args.get("content_pattern", "")
        max_results = args.get("max_results", 20)
        results = []
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", ".venv", "venv")]
            for fname in files:
                fp = Path(root) / fname
                if name_pat and not fnmatch.fnmatch(fname, name_pat):
                    continue
                if content_pat:
                    try:
                        text = fp.read_text(encoding="utf-8", errors="ignore")
                        if content_pat.lower() not in text.lower():
                            continue
                    except Exception:
                        continue
                results.append(_file_info(fp))
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
        return {"query_path": str(p), "count": len(results), "results": results}

    elif name == "create_directory":
        p = _safe_path(args["path"])
        p.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": str(p)}

    elif name == "copy_file":
        src = _safe_path(args["source"])
        dst = _safe_path(args["destination"])
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return {"ok": True, "source": str(src), "destination": str(dst)}

    elif name == "move_file":
        src = _safe_path(args["source"])
        dst = _safe_path(args["destination"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"ok": True, "source": str(src), "destination": str(dst)}

    elif name == "delete_file":
        p = _safe_path(args["path"])
        recursive = args.get("recursive", False)
        if p.is_dir():
            if recursive:
                shutil.rmtree(p)
            else:
                p.rmdir()  # only empty dirs
        else:
            p.unlink()
        return {"ok": True, "deleted": str(p)}

    elif name == "file_info":
        p = _safe_path(args["path"])
        if not p.exists():
            return {"error": f"Path not found: {args['path']}"}
        return _file_info(p)

    return {"error": f"Unknown tool: {name}"}


app.add_request_handler("tools/list", types.RequestParams, handle_list_tools)
app.add_request_handler("tools/call", types.CallToolRequestParams, handle_call_tool)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
