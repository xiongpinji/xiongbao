"""分块处理：大数据集分批执行。

功能：
- 将大列表分块处理（避免内存溢出）
- 进度回调
- 并发控制
- 错误隔离（单块失败不影响整体）

用法：
    from xagent.api.chunked_processing import process_chunks

    results = await process_chunks(
        items=large_list,
        processor=async_fn,
        chunk_size=100,
        concurrency=5,
        on_progress=lambda done, total: print(f"{done}/{total}"),
    )
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TypeVar

from xagent.infra.logging import get_logger

logger = get_logger("xagent.chunked")

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class ChunkResult:
    """分块处理结果。"""

    total: int
    succeeded: int
    failed: int
    results: list[Any] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0


def chunk_list(items: list, chunk_size: int) -> list[list]:
    """将列表分块。"""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


async def process_chunks(
    items: list[Any],
    processor: Callable[[Any], Coroutine[Any, Any, Any]],
    chunk_size: int = 100,
    concurrency: int = 5,
    on_progress: Callable[[int, int], None] | None = None,
    stop_on_error: bool = False,
) -> ChunkResult:
    """分块并发处理。"""
    start = time.perf_counter()
    chunks = chunk_list(items, chunk_size)
    total = len(items)
    done_count = 0
    results: list[Any] = []
    errors: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(item: Any, index: int) -> Any:
        async with semaphore:
            return await processor(item)

    for chunk_idx, chunk in enumerate(chunks):
        offset = chunk_idx * chunk_size
        tasks = [
            process_one(item, offset + i)
            for i, item in enumerate(chunk)
        ]

        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(chunk_results):
            if isinstance(result, Exception):
                errors.append({
                    "index": offset + i,
                    "error": str(result),
                    "type": type(result).__name__,
                })
                if stop_on_error:
                    break
            else:
                results.append(result)

        done_count += len(chunk)
        on_progress?.(done_count, total)

        if stop_on_error and errors:
            break

    duration = (time.perf_counter() - start) * 1000

    result = ChunkResult(
        total=total,
        succeeded=len(results),
        failed=len(errors),
        results=results,
        errors=errors,
        duration_ms=round(duration, 1),
    )

    logger.info(
        "chunked processing done: %d/%d ok, %d failed (%.0fms)",
        result.succeeded, total, result.failed, duration,
    )
    return result


async def process_generator(
    source,
    processor: Callable[[Any], Coroutine[Any, Any, Any]],
    batch_size: int = 50,
    concurrency: int = 3,
):
    """流式分块处理（生成器模式，节省内存）。"""
    batch: list[Any] = []
    semaphore = asyncio.Semaphore(concurrency)

    async def process_item(item):
        async with semaphore:
            return await processor(item)

    async for item in source:
        batch.append(item)
        if len(batch) >= batch_size:
            tasks = [process_item(i) for i in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if not isinstance(r, Exception):
                    yield r
            batch = []

    # 处理剩余
    if batch:
        tasks = [process_item(i) for i in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if not isinstance(r, Exception):
                yield r
