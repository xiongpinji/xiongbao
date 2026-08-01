"""服务熔断器：防止级联故障（Circuit Breaker 模式）。

三态模型：
- CLOSED（正常）：请求正常通过
- OPEN（熔断）：连续失败达阈值 → 快速失败，不再调用下游
- HALF_OPEN（探测）：冷却期后放行少量请求探测恢复

用法：
    from xagent.api.circuit_breaker import CircuitBreaker
    breaker = CircuitBreaker(name="llm", failure_threshold=5, recovery_timeout=30)

    @breaker.protect
    async def call_llm(prompt: str):
        ...
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable

from xagent.infra.logging import get_logger

logger = get_logger("xagent.breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStats:
    """熔断器统计。"""

    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = field(default_factory=time.time)


class CircuitBreaker:
    """熔断器实例。"""

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        """当前状态（含自动转换逻辑）。"""
        if self._state == CircuitState.OPEN:
            # 冷却期到 → 转为 HALF_OPEN
            if time.time() - self._stats.last_failure_time >= self.recovery_timeout:
                self._transition(CircuitState.HALF_OPEN)
                self._half_open_calls = 0
        return self._state

    def _transition(self, new_state: CircuitState):
        old = self._state
        self._state = new_state
        self._stats.last_state_change = time.time()
        logger.info("circuit_transition", breaker=self.name, from_state=old.value, to_state=new_state.value)

    def record_success(self):
        """记录成功。"""
        self._stats.total_calls += 1
        self._stats.total_successes += 1
        self._stats.consecutive_failures = 0

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._transition(CircuitState.CLOSED)

    def record_failure(self):
        """记录失败。"""
        self._stats.total_calls += 1
        self._stats.total_failures += 1
        self._stats.consecutive_failures += 1
        self._stats.last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # 探测失败 → 重新熔断
            self._transition(CircuitState.OPEN)
        elif self._stats.consecutive_failures >= self.failure_threshold:
            self._transition(CircuitState.OPEN)

    def protect(self, fn: Callable) -> Callable:
        """装饰器：保护异步函数。"""

        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            state = self.state  # 触发自动转换

            if state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"熔断器 [{self.name}] 已开启，{self.recovery_timeout}s 后重试"
                )

            try:
                result = await fn(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure()
                raise

        return wrapper

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self._stats.total_calls,
            "total_failures": self._stats.total_failures,
            "consecutive_failures": self._stats.consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


class CircuitOpenError(Exception):
    """熔断器开启时抛出。"""

    pass


# ─── 预置熔断器实例 ───

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    """获取或创建命名熔断器。"""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name=name, **kwargs)
    return _breakers[name]


def all_breaker_stats() -> list[dict]:
    """所有熔断器状态。"""
    return [b.stats for b in _breakers.values()]
