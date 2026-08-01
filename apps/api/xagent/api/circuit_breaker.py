"""断路器：下游服务故障自动熔断。

功能：
- 三态：closed → open → half-open
- 失败率/连续失败触发
- 半开探测恢复
- 按服务名隔离

用法：
    from xagent.api.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(failure_threshold=5, recovery_timeout_s=30)

    @cb.guard("payment-service")
    async def call_payment():
        ...
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStats:
    """断路器统计。"""

    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = field(default_factory=time.time)


class CircuitBreaker:
    """断路器。"""

    def __init__(
        self,
        failure_threshold: int = 5,
        failure_rate_threshold: float = 0.5,
        recovery_timeout_s: float = 30.0,
        half_open_max_calls: int = 3,
        window_size: int = 20,
    ):
        self.failure_threshold = failure_threshold
        self.failure_rate_threshold = failure_rate_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.half_open_max_calls = half_open_max_calls
        self.window_size = window_size

        self._circuits: dict[str, _Circuit] = {}

    def _get_circuit(self, name: str) -> _Circuit:
        if name not in self._circuits:
            self._circuits[name] = _Circuit(
                name=name,
                failure_threshold=self.failure_threshold,
                failure_rate_threshold=self.failure_rate_threshold,
                recovery_timeout_s=self.recovery_timeout_s,
                half_open_max_calls=self.half_open_max_calls,
                window_size=self.window_size,
            )
        return self._circuits[name]

    def guard(self, name: str):
        """装饰器：保护异步函数。"""

        def decorator(fn: Callable[..., Coroutine[Any, Any, Any]]):
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                circuit = self._get_circuit(name)
                return await circuit.call(fn, *args, **kwargs)

            wrapper.__name__ = fn.__name__
            return wrapper

        return decorator

    async def call(self, name: str, fn: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> Any:
        """直接调用。"""
        circuit = self._get_circuit(name)
        return await circuit.call(fn, *args, **kwargs)

    def get_state(self, name: str) -> CircuitState:
        """获取断路器状态。"""
        return self._get_circuit(name).state

    def get_stats(self, name: str) -> dict[str, Any]:
        """获取统计信息。"""
        circuit = self._get_circuit(name)
        return {
            "name": name,
            "state": circuit.state.value,
            "total_calls": circuit.stats.total_calls,
            "total_failures": circuit.stats.total_failures,
            "consecutive_failures": circuit.stats.consecutive_failures,
        }

    def reset(self, name: str) -> None:
        """手动重置。"""
        if name in self._circuits:
            self._circuits[name].reset()

    def list_circuits(self) -> list[dict[str, Any]]:
        """列出所有断路器。"""
        return [self.get_stats(name) for name in self._circuits]


class CircuitOpenError(Exception):
    """断路器打开异常。"""

    def __init__(self, name: str, retry_after_s: float):
        self.name = name
        self.retry_after_s = retry_after_s
        super().__init__(f"Circuit '{name}' is OPEN, retry after {retry_after_s:.1f}s")


class _Circuit:
    """单个断路器实例。"""

    def __init__(
        self,
        name: str,
        failure_threshold: int,
        failure_rate_threshold: float,
        recovery_timeout_s: float,
        half_open_max_calls: int,
        window_size: int,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.failure_rate_threshold = failure_rate_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.half_open_max_calls = half_open_max_calls
        self.window_size = window_size

        self.state = CircuitState.CLOSED
        self.stats = CircuitStats()
        self._results: list[bool] = []  # True=success
        self._half_open_calls = 0

    async def call(self, fn: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> Any:
        """执行调用。"""
        self._check_state_transition()

        if self.state == CircuitState.OPEN:
            retry_after = self.recovery_timeout_s - (time.time() - self.stats.last_failure_time)
            raise CircuitOpenError(self.name, max(0, retry_after))

        if self.state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitOpenError(self.name, 1.0)
            self._half_open_calls += 1

        self.stats.total_calls += 1

        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self.stats.total_successes += 1
        self.stats.consecutive_failures = 0
        self._results.append(True)
        self._trim_window()

        if self.state == CircuitState.HALF_OPEN:
            # 半开成功 → 关闭
            self._transition(CircuitState.CLOSED)
            self._half_open_calls = 0

    def _on_failure(self) -> None:
        self.stats.total_failures += 1
        self.stats.consecutive_failures += 1
        self.stats.last_failure_time = time.time()
        self._results.append(False)
        self._trim_window()

        if self.state == CircuitState.HALF_OPEN:
            # 半开失败 → 重新打开
            self._transition(CircuitState.OPEN)
            self._half_open_calls = 0
            return

        # 检查是否需要打开
        if self.stats.consecutive_failures >= self.failure_threshold:
            self._transition(CircuitState.OPEN)
        elif len(self._results) >= self.window_size:
            failure_rate = self._results.count(False) / len(self._results)
            if failure_rate >= self.failure_rate_threshold:
                self._transition(CircuitState.OPEN)

    def _check_state_transition(self) -> None:
        """检查 OPEN → HALF_OPEN 转换。"""
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.stats.last_failure_time
            if elapsed >= self.recovery_timeout_s:
                self._transition(CircuitState.HALF_OPEN)
                self._half_open_calls = 0

    def _transition(self, new_state: CircuitState) -> None:
        old = self.state
        self.state = new_state
        self.stats.last_state_change = time.time()
        if new_state == CircuitState.CLOSED:
            self._results.clear()
            self.stats.consecutive_failures = 0
        logger.info("circuit [%s]: %s → %s", self.name, old.value, new_state.value)

    def _trim_window(self) -> None:
        if len(self._results) > self.window_size:
            self._results = self._results[-self.window_size:]

    def reset(self) -> None:
        self.state = CircuitState.CLOSED
        self.stats = CircuitStats()
        self._results.clear()
        self._half_open_calls = 0


# 全局实例
circuit_breaker = CircuitBreaker()
