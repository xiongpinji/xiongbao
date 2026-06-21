"""内置工具：最小可用集合。MCP / Composio 工具在各自 adapter 注册进同一注册表。

- memory_search：检索当前租户记忆（演示 RAG 闭环）。
- memory_write  ：写入一条记忆到当前租户。
- echo          ：回显（调试 / 占位）。
所有工具严格用 ctx.principal.tenant_id 做租户隔离。
"""

from __future__ import annotations

from typing import Any

from xagent.adapters.memory import MemoryRecord, get_vector_store
from xagent.adapters.tools.base import Tool, ToolContext, ToolResult, ToolSpec


class EchoTool:
    spec = ToolSpec(
        name="echo",
        description="回显输入文本，用于调试。",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, output=args.get("text", ""))


class MemorySearchTool:
    spec = ToolSpec(
        name="memory_search",
        description="在当前租户的记忆库中按语义检索相关条目。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(ok=False, error="query 不能为空")
        hits = await get_vector_store().search(
            query, top_k=int(args.get("top_k", 5)), tenant_id=ctx.principal.tenant_id
        )
        return ToolResult(
            ok=True,
            output=[{"id": h.id, "text": h.text, "score": h.score} for h in hits],
        )


class MemoryWriteTool:
    spec = ToolSpec(
        name="memory_write",
        description="向当前租户记忆库写入一条文本记忆。",
        parameters={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["id", "text"],
        },
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        rid = args.get("id")
        text = args.get("text")
        if not rid or not text:
            return ToolResult(ok=False, error="id 与 text 必填")
        await get_vector_store().upsert(
            [MemoryRecord(id=rid, text=text, metadata={"tenant_id": ctx.principal.tenant_id})]
        )
        return ToolResult(ok=True, output={"written": rid})


def builtin_tools() -> list[Tool]:
    return [EchoTool(), MemorySearchTool(), MemoryWriteTool()]
