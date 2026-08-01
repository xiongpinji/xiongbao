"""流式响应：SSE / NDJSON 分块输出。

功能：
- Server-Sent Events (SSE) 生成器
- NDJSON 流式输出
- 心跳保活
- 客户端断开检测

用法：
    from xagent.api.streaming import sse_response, ndjson_stream

    @router.get("/api/v1/runs/{run_id}/events")
    async def stream_events(run_id: str):
        async def generator():
            async for event in run_events(run_id):
                yield {"event": "progress", "data": event}
        return sse_response(generator())
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator

from starlette.requests import Request
from starlette.responses import StreamingResponse

from xagent.infra.logging import get_logger

logger = get_logger("xagent.streaming")


async def _sse_encoder(
    source: AsyncGenerator[dict[str, Any], None],
    heartbeat_interval: float = 15.0,
) -> AsyncGenerator[str, None]:
    """将事件字典编码为 SSE 格式。"""
    last_send = time.time()

    async for event in source:
        event_type = event.get("event", "message")
        data = event.get("data", {})
        event_id = event.get("id")

        lines = []
        if event_id:
            lines.append(f"id: {event_id}")
        if event_type != "message":
            lines.append(f"event: {event_type}")

        # data 可以是多行
        data_str = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
        for line in data_str.split("\n"):
            lines.append(f"data: {line}")

        lines.append("")  # 空行结束事件
        lines.append("")
        yield "\n".join(lines)
        last_send = time.time()

    # 结束标记
    yield "event: done\ndata: {}\n\n"


async def _heartbeat_wrapper(
    source: AsyncGenerator[str, None],
    interval: float = 15.0,
) -> AsyncGenerator[str, None]:
    """添加心跳保活。"""
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def producer():
        async for chunk in source:
            await queue.put(chunk)
        await queue.put(None)

    task = asyncio.create_task(producer())

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=interval)
                if chunk is None:
                    break
                yield chunk
            except asyncio.TimeoutError:
                # 心跳
                yield ": heartbeat\n\n"
    finally:
        task.cancel()


def sse_response(
    source: AsyncGenerator[dict[str, Any], None],
    heartbeat_interval: float = 15.0,
    headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """创建 SSE 流式响应。"""
    encoded = _sse_encoder(source, heartbeat_interval)
    with_heartbeat = _heartbeat_wrapper(encoded, heartbeat_interval)

    return StreamingResponse(
        with_heartbeat,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            **(headers or {}),
        },
    )


async def _ndjson_encoder(
    source: AsyncGenerator[dict[str, Any], None],
) -> AsyncGenerator[str, None]:
    """NDJSON 编码器。"""
    async for item in source:
        yield json.dumps(item, ensure_ascii=False) + "\n"


def ndjson_stream(
    source: AsyncGenerator[dict[str, Any], None],
    headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """创建 NDJSON 流式响应。"""
    return StreamingResponse(
        _ndjson_encoder(source),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            **(headers or {}),
        },
    )


async def client_disconnected(request: Request) -> bool:
    """检测客户端是否已断开。"""
    return await request.is_disconnected()
