"""指标收集：轻量级应用指标聚合。

功能：
- Counter / Gauge / Histogram
- 标签维度
- 快照导出

用法：
    from xagent.api.metrics_collector import metrics

    metrics.increment("requests_total", tags={"method": "GET"})
    metrics.gauge("active_connections", 42)
    metrics.observe("response_time_ms", 123.4)
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from xagent.infra.logging import get_logger

logger = get_logger("xagent.metrics")


def _tags_key(tags: dict[str, str] | None) -> str:
    if not tags:
        return ""
    return ",".join(f"{k}={v}" for k, v in sorted(tags.items()))


@dataclass
class HistogramBucket:
    """直方图桶。"""

    buckets: list[float] = field(default_factory=lambda: [1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000])
    counts: list[int] = field(default_factory=list)
    total: float = 0.0
    count: int = 0

    def __post_init__(self):
        self.counts = [0] * (len(self.buckets) + 1)

    def observe(self, value: float) -> None:
        self.total += value
        self.count += 1
        for i, bound in enumerate(self.buckets):
            if value <= bound:
                self.counts[i] += 1
                return
        self.counts[-1] += 1  # +Inf


class MetricsCollector:
    """指标收集器。"""

    def __init__(self):
        self._counters: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: dict[str, dict[str, HistogramBucket]] = defaultdict(lambda: defaultdict(HistogramBucket))
        self._created_at = time.time()

    def increment(self, name: str, value: float = 1.0, tags: dict[str, str] | None = None) -> None:
        """递增计数器。"""
        key = _tags_key(tags)
        self._counters[name][key] += value

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """设置仪表盘值。"""
        key = _tags_key(tags)
        self._gauges[name][key] = value

    def observe(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """记录直方图观测值。"""
        key = _tags_key(tags)
        self._histograms[name][key].observe(value)

    def get_counter(self, name: str, tags: dict[str, str] | None = None) -> float:
        """获取计数器值。"""
        return self._counters.get(name, {}).get(_tags_key(tags), 0.0)

    def get_gauge(self, name: str, tags: dict[str, str] | None = None) -> float:
        """获取仪表盘值。"""
        return self._gauges.get(name, {}).get(_tags_key(tags), 0.0)

    def snapshot(self) -> dict[str, Any]:
        """导出快照。"""
        result: dict[str, Any] = {
            "uptime_s": round(time.time() - self._created_at, 1),
            "counters": {},
            "gauges": {},
            "histograms": {},
        }

        for name, tag_map in self._counters.items():
            result["counters"][name] = dict(tag_map)

        for name, tag_map in self._gauges.items():
            result["gauges"][name] = dict(tag_map)

        for name, tag_map in self._histograms.items():
            result["histograms"][name] = {}
            for key, bucket in tag_map.items():
                result["histograms"][name][key or "_"] = {
                    "count": bucket.count,
                    "total": round(bucket.total, 2),
                    "avg": round(bucket.total / max(1, bucket.count), 2),
                }

        return result

    def reset(self) -> None:
        """重置所有指标。"""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()


# 全局实例
metrics = MetricsCollector()
