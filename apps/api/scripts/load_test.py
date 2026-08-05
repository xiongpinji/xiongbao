"""X-Agent API 容量压测基线脚本（httpx + asyncio，无外部依赖）。

用法:
    python apps/api/scripts/load_test.py --url http://127.0.0.1:8010 \
        --targets health,skills,canvas,login

设计要点（2026-08-03 基线）:
    - 服务端 RateLimitMiddleware: 非豁免端点 300 req / 60s / 客户端 IP（main.py 硬编码）。
      /health /ready /metrics 豁免。
    - 因此对鉴权端点采用"干净突发"法：每档并发一轮 ≤280 请求的突发，
      轮间 sleep 65s 等滑动窗口排空，保证 0 个 429 干扰延迟数据。
    - login 自身被 bcrypt 限速（~4 RPS），天然不超窗口，无需等待。

压测端点（非 LLM）:
    GET  /health            基线（限流豁免）
    POST /api/v1/auth/login 写路径 + JWT 签发
    GET  /api/v1/skills     鉴权读路径
    GET  /api/v1/canvas     鉴权读 + DB

输出: 进度行 + RESULTS_JSON_BEGIN/END 之间的 JSON 数组。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass, field

import httpx

BURST_N = 250          # 每档突发请求数（≥200，< 服务端 300/60s 窗口）
WINDOW_WAIT = 65.0     # 滑动窗口排空等待


@dataclass
class Result:
    endpoint: str
    concurrency: int
    total: int
    ok: int
    errors: int
    error_rate: float
    rps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    avg_ms: float
    max_ms: float
    status_counts: dict[str, int] = field(default_factory=dict)


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(int(len(sorted_vals) * p), len(sorted_vals) - 1)
    return sorted_vals[idx]


async def _do_request(
    client: httpx.AsyncClient, method: str, url: str, headers: dict, body: dict | None
) -> tuple[float, int]:
    start = time.perf_counter()
    try:
        resp = await client.request(method, url, headers=headers, json=body)
        return (time.perf_counter() - start) * 1000, resp.status_code
    except Exception:
        return (time.perf_counter() - start) * 1000, -1


async def run_one(
    client: httpx.AsyncClient,
    name: str,
    method: str,
    url: str,
    headers: dict,
    body: dict | None,
    n: int,
    concurrency: int,
) -> Result:
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    status_counts: dict[str, int] = {}
    lock = asyncio.Lock()

    async def worker() -> None:
        async with sem:
            lat, status = await _do_request(client, method, url, headers, body)
            async with lock:
                latencies.append(lat)
                key = str(status)
                status_counts[key] = status_counts.get(key, 0) + 1

    # 预热（豁免端点才预热，避免消耗限流预算）
    if url.endswith("/health"):
        for _ in range(3):
            await _do_request(client, method, url, headers, body)

    t0 = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(n)))
    total_time = time.perf_counter() - t0

    ok = status_counts.get("200", 0)
    errors = n - ok
    latencies.sort()
    return Result(
        endpoint=name,
        concurrency=concurrency,
        total=n,
        ok=ok,
        errors=errors,
        error_rate=round(errors / n * 100, 2),
        rps=round(n / total_time, 1),
        p50_ms=round(_pct(latencies, 0.50), 2),
        p95_ms=round(_pct(latencies, 0.95), 2),
        p99_ms=round(_pct(latencies, 0.99), 2),
        avg_ms=round(statistics.mean(latencies), 2) if latencies else 0.0,
        max_ms=round(latencies[-1], 2) if latencies else 0.0,
        status_counts=status_counts,
    )


async def soak(
    client: httpx.AsyncClient,
    base: str,
    auth: dict,
    args: argparse.Namespace,
) -> None:
    """持续压测（soak）：混合端点、固定并发、按时长运行，周期性输出进度。

    用于 >=10min 稳定性/内存泄漏观察（配合外部 RSS 采样），区别于突发式基线。
    """
    duration = args.duration
    concurrency = int(args.concurrency.split(",")[0])
    endpoints = [
        ("GET", f"{base}/health", {}, None),
        ("GET", f"{base}/api/v1/skills", auth, None),
        ("GET", f"{base}/api/v1/canvas", auth, None),
    ]
    stop = time.perf_counter() + duration
    latencies: list[float] = []
    status_counts: dict[str, int] = {}
    lock = asyncio.Lock()
    counter = 0

    async def worker() -> None:
        nonlocal counter
        while time.perf_counter() < stop:
            method, url, headers, body = endpoints[counter % len(endpoints)]
            counter += 1
            lat, status = await _do_request(client, method, url, headers, body)
            async with lock:
                latencies.append(lat)
                key = str(status)
                status_counts[key] = status_counts.get(key, 0) + 1

    t0 = time.perf_counter()
    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    while time.perf_counter() < stop:
        await asyncio.sleep(60)
        done = len(latencies)
        el = time.perf_counter() - t0
        print(f"[soak] {el/60:.1f}min total={done} rps={done/el:.1f} "
              f"status={status_counts}", flush=True)
    await asyncio.gather(*workers)
    total_time = time.perf_counter() - t0
    n = len(latencies)
    latencies.sort()
    r = Result(
        endpoint="soak:mixed(health,skills,canvas)",
        concurrency=concurrency, total=n,
        ok=status_counts.get("200", 0),
        errors=n - status_counts.get("200", 0),
        error_rate=round((n - status_counts.get("200", 0)) / max(n, 1) * 100, 2),
        rps=round(n / total_time, 1),
        p50_ms=round(_pct(latencies, 0.50), 2),
        p95_ms=round(_pct(latencies, 0.95), 2),
        p99_ms=round(_pct(latencies, 0.99), 2),
        avg_ms=round(statistics.mean(latencies), 2) if latencies else 0.0,
        max_ms=round(latencies[-1], 2) if latencies else 0.0,
        status_counts=status_counts,
    )
    print("RESULTS_JSON_BEGIN")
    print(json.dumps([asdict(r)], ensure_ascii=False, indent=2))
    print("RESULTS_JSON_END")


async def main_async(args: argparse.Namespace) -> None:
    base = args.url.rstrip("/")
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=200)
    async with httpx.AsyncClient(timeout=60, limits=limits) as client:
        resp = await client.post(
            f"{base}/api/v1/auth/login",
            json={"username": args.user, "password": args.password},
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        if args.duration > 0:
            await soak(client, base, auth, args)
            return

        all_targets = {
            "health": ("GET /health", "GET", f"{base}/health", {}, None, False),
            "login": ("POST /api/v1/auth/login", "POST", f"{base}/api/v1/auth/login",
                      {}, {"username": args.user, "password": args.password}, True),
            "skills": ("GET /api/v1/skills", "GET", f"{base}/api/v1/skills", auth, None, True),
            "canvas": ("GET /api/v1/canvas", "GET", f"{base}/api/v1/canvas", auth, None, True),
        }
        wanted = [t.strip() for t in args.targets.split(",") if t.strip()]
        concurrencies = [int(c) for c in args.concurrency.split(",")]

        wait_s = args.wait
        # 初始登录消耗了 1 次预算，先排空
        if wait_s > 0 and any(all_targets[t][5] for t in wanted):
            print(f"[wait] 初始 {wait_s}s 排空限流窗口...", flush=True)
            await asyncio.sleep(wait_s)

        results: list[dict] = []
        for t in wanted:
            name, method, url, headers, body, limited = all_targets[t]
            for i, c in enumerate(concurrencies):
                if limited and i > 0 and wait_s > 0:
                    print(f"[wait] {wait_s}s 排空限流窗口...", flush=True)
                    await asyncio.sleep(wait_s)
                n = max(args.requests, BURST_N)
                r = await run_one(client, name, method, url, headers, body, n, c)
                results.append(asdict(r))
                print(
                    f"[done] {name} c={c} n={n} rps={r.rps} "
                    f"p50={r.p50_ms}ms p95={r.p95_ms}ms p99={r.p99_ms}ms "
                    f"err={r.error_rate}% status={r.status_counts}",
                    flush=True,
                )

        print("RESULTS_JSON_BEGIN")
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print("RESULTS_JSON_END")


def main() -> None:
    parser = argparse.ArgumentParser(description="X-Agent API 压测基线")
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--targets", default="health,login,skills,canvas")
    parser.add_argument("--concurrency", default="1,10,50")
    parser.add_argument("--requests", type=int, default=BURST_N, help="每档请求数")
    parser.add_argument("--wait", type=float, default=WINDOW_WAIT,
                        help="限流窗口排空等待秒数；服务端关闭限流时传 0")
    parser.add_argument("--duration", type=float, default=0,
                        help="soak 模式：持续压测秒数（>0 时启用，并发取 --concurrency 首档）")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
