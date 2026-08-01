"""慢查询日志：记录耗时超阈值的操作。

功能：
- 装饰器标记慢操作
- 可配置阈值（默认 1s）
- 结构化日志输出（操作名/耗时/参数摘要）
- 统计聚合（P50/P95/P99）

用法：
    from xagent.api.slow_query import slow_query, slow_query_stats

    @slow_query(threshold=0.5, name="agent_run")
    async def run_agent(prompt: str) -> str:
        ...

    # 查看统计：
    stats = slow_query_stats()
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.slow_query")


@dataclass
class QueryRecord:
    """慢查询记录。"""

    name: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)
    args_summary: str = ""


@dataclass
class QueryStats:
    """操作统计。"""

    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    min_ms: float = float("inf")
    slow_count: int = 0
    durations: list[float] = field(default_factory=list)

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0

    @property
    def p50(self) -> float:
        return self._percentile(50)

    @property
    def p95(self) -> float:
        return self._percentile(95)

    @property
    def p99(self) -> float:
        return self._percentile(99)

    def _percentile(self, p: int) -> float:
        if not self.durations:
            return 0
        sorted_d = sorted(self.durations)
        idx = int(len(sorted_d) * p / 100)
        idx = min(idx, len(sorted_d) - 1)
        return sorted_d[idx]


class SlowQueryTracker:
    """慢查询追踪器。"""

    def __init__(self, max_records: int = 1000):
        self._records: list[QueryRecord] = []
        self._stats: dict[str, QueryStats] = defaultdict(QueryStats)
        self._max_records = max_records

    def record(self, name: str, duration_ms: float, threshold_ms: float, args_summary: str = "") -> None:
        """记录一次操作。"""
        stats = self._stats[name]
        stats.count += 1
        stats.total_ms += duration_ms
        stats.max_ms = max(stats.max_ms, duration_ms)
        stats.min_ms = min(stats.min_ms, duration_ms)
        stats.durations.append(duration_ms)

        # 限制 durations 列表大小
        if len(stats.durations) > 500:
            stats.durations = stats.durations[-250:]

        # 超阈值 → 记录 + 告警日志
        if duration_ms >= threshold_ms:
            stats.slow_count += 1
            record = QueryRecord(
                name=name,
                duration_ms=round(duration_ms, 1),
                args_summary=args_summary[:200],
            )
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records :]

            logger.warning(
                "SLOW QUERY: %s took %.1fms (threshold=%.1fms) %s",
                name,
                duration_ms,
                threshold_ms,
                args_summary[:100],
            )

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """获取所有操作统计。"""
        result = {}
        for name, stats in self._stats.items():
            result[name] = {
                "count": stats.count,
                "slow_count": stats.slow_count,
                "avg_ms": round(stats.avg_ms, 1),
                "max_ms": round(stats.max_ms, 1),
                "min_ms": round(stats.min_ms, 1) if stats.min_ms != float("inf") else 0,
                "p50_ms": round(stats.p50, 1),
                "p95_ms": round(stats.p95, 1),
                "p99_ms": round(stats.p99, 1),
            }
        return result

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取最近的慢查询记录。"""
        return [
            {
                "name": r.name,
                "duration_ms": r.duration_ms,
                "timestamp": r.timestamp,
                "args_summary": r.args_summary,
            }
            for r in self._records[-limit:]
        ]


# 全局追踪器
_tracker = SlowQueryTracker()


def slow_query(
    threshold: float = 1.0,
    name: str | None = None,
) -> Callable:
    """装饰器：追踪慢操作。

    Args:
        threshold: 慢查询阈值（秒）
        name: 操作名称（默认用函数名）
    """

    def decorator(fn: Callable[..., Coroutine]) -> Callable:
        op_name = name or fn.__qualname__

        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                # 参数摘要
                args_summary = ""
                if args:
                    args_summary = str(args[0])[:100]
                elif kwargs:
                    first_key = next(iter(kwargs), "")
                    args_summary = f"{first_key}={str(kwargs[first_key])[:80]}"

                _tracker.record(
                    op_name, duration_ms, threshold * 1000, args_summary
                )

        return wrapper

    return decorator


def slow_query_stats() -> dict[str, dict[str, Any]]:
    """获取慢查询统计。"""
    return _tracker.get_stats()


def slow_query_recent(limit: int = 20) -> list[dict[str, Any]]:
    """获取最近慢查询。"""
    return _tracker.get_recent(limit)
