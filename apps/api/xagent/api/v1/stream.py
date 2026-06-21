"""流式路由：Agent 运行 SSE（逐 token / 事件推送）。

用 StreamingResponse + async generator，把编排事件实时推给前端。
lite/mock 模式下仍能产出事件流（非真实 token，但 SSE 通道可用）。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from xagent.core.orchestration import run_agent
from xagent.enterprise.auth.principal import Principal
from xagent.enterprise.authz.guards import require_permission

router = APIRouter(prefix="/stream", tags=["stream"])


class StreamRunIn(BaseModel):
    goal: str = Field(..., min_length=1)
    role: str | None = None
    capabilities: list[str] = Field(default_factory=list)


async def _event_stream(
    goal: str, principal: Principal, role: str | None, caps: list[str]
) -> AsyncGenerator[bytes, None]:
    """跑 agent 并把事件逐条以 SSE 实时推送（step 级流式）。"""
    yield _sse("started", {"goal": goal})

    queue: asyncio.Queue = asyncio.Queue()
    done = object()

    async def on_event(ev) -> None:
        await queue.put(
            _sse(
                ev.kind.value,
                {
                    "kind": ev.kind.value,
                    "step": ev.step,
                    "tool": ev.tool,
                    "content": ev.content,
                },
            )
        )

    async def _run():
        try:
            result = await run_agent(
                goal, principal=principal, role_name=role,
                capabilities=set(caps) or None, on_event=on_event,
            )
            await queue.put(
                _sse("done", {"steps": result.steps, "run_id": result.run_id})
            )
        except Exception as exc:
            await queue.put(_sse("error", {"error": str(exc)}))
        finally:
            await queue.put(done)

    task = asyncio.create_task(_run())
    try:
        while True:
            item = await queue.get()
            if item is done:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
    yield _sse("end", {})


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


@router.post("/agents/run", summary="Agent 运行 SSE 流")
async def stream_run(
    body: StreamRunIn,
    principal: Principal = Depends(require_permission("agent", "execute")),
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(body.goal, principal, body.role, body.capabilities),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
