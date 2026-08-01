"""请求聚合：并行调用多服务合并响应。

功能：
- 并行调用多个数据源
- 超时独立控制
- 部分失败降级
- 结果合并策略

用法：
    from xagent.api.aggregator import Aggregator

    agg = Aggregator()
    agg.add("agents", fetch_agents, timeout=5.0)
    agg.add("workflows", fetch_workflows, timeout=3.0)
    result = await agg.execute()
    # {"agents": [...], "workflows": [...], "_errors": {}}
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.aggregator")


@dataclass
class AggregateSource:
    """聚合数据源。"""

    name: str
    fn: Callable[[], Coroutine[Any, Any, Any]]
    timeout: float = 10.0
    required: bool = False  # 必须成功
    default: Any = None  # 失败时的默认值


@dataclass
class AggregateResult:
    """聚合结果。"""

    data: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    latencies: dict[str, float] = field(default_factory=dict)
    total_ms: float = 0.0


class Aggregator:
    """请求聚合器。"""

    def __init__(self):
        self._sources: list[AggregateSource] = []

    def add(
        self,
        name: str,
        fn: Callable[[], Coroutine[Any, Any, Any]],
        timeout: float = 10.0,
        required: bool = False,
        default: Any = None,
    ) -> "Aggregator":
        """添加数据源。"""
        self._sources.append(
            AggregateSource(name=name, fn=fn, timeout=timeout, required=required, default=default)
        )
        return self

    async def execute(self) -> AggregateResult:
        """并行执行所有数据源。"""
        start = time.perf_counter()
        result = AggregateResult()

        tasks = [self._fetch_one(source) for source in self._sources]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for source, outcome in zip(self._sources, outcomes):
            if isinstance(outcome, Exception):
                result.errors[source.name] = str(outcome)[:200]
                result.data[source.name] = source.default
                if source.required:
                    logger.error("required source failed: %s — %s", source.name, outcome)
            elif isinstance(outcome, tuple):
                data, latency = outcome
                result.data[source.name] = data
                result.latencies[source.name] = latency

        result.total_ms = round((time.perf_counter() - start) * 1000, 1)
        return result

    async def _fetch_one(self, source: AggregateSource) -> tuple[Any, float]:
        """获取单个数据源。"""
        start = time.perf_counter()
        try:
            data = await asyncio.wait_for(source.fn(), timeout=source.timeout)
            latency = round((time.perf_counter() - start) * 1000, 1)
            return data, latency
        except asyncio.TimeoutError:
            raise TimeoutError(f"{source.name} timeout ({source.timeout}s)")
