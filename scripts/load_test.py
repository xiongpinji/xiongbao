"""轻量级 API 压测脚本（纯 Python，无外部依赖）。

用法: python scripts/load_test.py [--url http://127.0.0.1:8000] [--n 100] [--c 10]
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

DEFAULT_URL = "http://127.0.0.1:8000"


async def single_request(client: httpx.AsyncClient, url: str, path: str) -> float | None:
    start = time.perf_counter()
    try:
        resp = await client.get(f"{url}{path}")
        elapsed = (time.perf_counter() - start) * 1000
        if resp.status_code != 200:
            return None
        return elapsed
    except Exception:
        return None


async def run_load_test(url: str, n: int, concurrency: int) -> None:
    paths = ["/health", "/api/v1/skills/stats", "/api/v1/mcp/servers", "/perf"]
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []

    async with httpx.AsyncClient(timeout=10) as client:
        # 预热
        for p in paths:
            await single_request(client, url, p)

        async def worker(i: int) -> None:
            async with sem:
                path = paths[i % len(paths)]
                lat = await single_request(client, url, path)
                if lat is not None:
                    latencies.append(lat)

        print(f"压测开始: {n} 请求, 并发={concurrency}, 目标={url}")
        t0 = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(n)))
        total_time = time.perf_counter() - t0

    # 统计
    if not latencies:
        print("\n所有请求失败，无法统计")
        return
    latencies.sort()
    print(f"\n{'='*50}")
    print(f"总请求: {len(latencies)}")
    print(f"总耗时: {total_time:.2f}s")
    print(f"QPS:    {len(latencies)/total_time:.1f}")
    print(f"P50:    {latencies[int(len(latencies)*0.5)]:.1f}ms")
    print(f"P95:    {latencies[min(int(len(latencies)*0.95), len(latencies)-1)]:.1f}ms")
    print(f"P99:    {latencies[min(int(len(latencies)*0.99), len(latencies)-1)]:.1f}ms")
    print(f"Max:    {latencies[-1]:.1f}ms")
    print(f"Avg:    {statistics.mean(latencies):.1f}ms")
    print(f"{'='*50}")


def main() -> None:
    parser = argparse.ArgumentParser(description="X-Agent API 压测")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--n", type=int, default=100, help="总请求数")
    parser.add_argument("--c", type=int, default=10, help="并发数")
    args = parser.parse_args()
    asyncio.run(run_load_test(args.url, args.n, args.c))


if __name__ == "__main__":
    main()
