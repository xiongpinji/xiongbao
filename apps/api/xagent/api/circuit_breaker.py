"""熔断器：防止级联故障。

功能：
- 三态：CLOSED → OPEN → HALF_OPEN → CLOSED
- 失败率阈值触发熔断
- 半开状态探测恢复
- 按服务名隔离

用法：
    from xagent.api.circuit_breaker import circuit_breaker

    @circuit_breaker.protect("llm_api", failure_threshold=5, recovery_timeout=30)
    async def call_llm(prompt: str) -> str:
        return await llm_client.complete(prompt)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.circuit")


class CircuitState(str, Enum):
    CLOSED = "closed"  # 正常通行
    OPEN = "open"  # 熔断（拒绝请求）
    HALF_OPEN = "half_open"  # 探测恢复


class CircuitOpenError(Exception):
    """熔断器开启时抛出。"""

    def __init__(self, service: str, retry_after: float):
        self.service = service
        self.retry_after = retry_after
        super().__init__(
            f"Circuit open for '{service}', retry after {retry_after:.1f}s"
        )


@dataclass
class CircuitStats:
    """熔断器统计。"""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = field(default_factory=time.time)


@dataclass
class CircuitConfig:
    """熔断器配置。"""

    failure_threshold: int = 5  # 连续失败次数触发熔断
    recovery_timeout: float = 30.0  # 熔断后等待恢复时间（秒）
    half_open_max_calls: int = 3  # 半开状态最大探测次数
    success_threshold: int = 2  # 半开状态连续成功次数恢复


class CircuitBreaker:
    """单服务熔断器。"""

    def __init__(self, name: str, config: CircuitConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.stats = CircuitStats()
        self._consecutive_failures = 0
        self._half_open_successes = 0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    async def call(self, fn: Callable[..., Coroutine], *args: Any, **kwargs: Any) -> Any:
        """通过熔断器调用函数。"""
        async with self._lock:
            self._check_state_transition()

            if self.state == CircuitState.OPEN:
                self.stats.rejected_calls += 1
                retry_after = self._time_until_retry()
                raise CircuitOpenError(self.name, retry_after)

            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self.stats.rejected_calls += 1
                    raise CircuitOpenError(self.name, 1.0)
                self._half_open_calls += 1

        # 执行调用（锁外）
        self.stats.total_calls += 1
        try:
            result = await fn(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as exc:
            await self._on_failure()
            raise exc

    async def _on_success(self) -> None:
        async with self._lock:
            self.stats.successful_calls += 1
            self._consecutive_failures = 0

            if self.state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    async def _on_failure(self) -> None:
        async with self._lock:
            self.stats.failed_calls += 1
            self.stats.last_failure_time = time.time()
            self._consecutive_failures += 1

            if self.state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._consecutive_failures >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)

    def _check_state_transition(self) -> None:
        """检查是否需要状态转换（OPEN → HALF_OPEN）。"""
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.stats.last_state_change
            if elapsed >= self.config.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        old = self.state
        self.state = new_state
        self.stats.last_state_change = time.time()

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_successes = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0

        logger.info(
            "circuit '%s': %s → %s", self.name, old.value, new_state.value
        )

    def _time_until_retry(self) -> float:
        elapsed = time.time() - self.stats.last_state_change
        return max(0, self.config.recovery_timeout - elapsed)


class CircuitBreakerRegistry:
    """熔断器注册表。"""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, name: str, config: CircuitConfig | None = None) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config or CircuitConfig())
        return self._breakers[name]

    def protect(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> Callable:
        """装饰器：保护函数。"""
        config = CircuitConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        def decorator(fn: Callable[..., Coroutine]) -> Callable:
            breaker = self.get(name, config)

            @wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                return await breaker.call(fn, *args, **kwargs)

            return wrapper

        return decorator

    @property
    def states(self) -> dict[str, str]:
        return {name: cb.state.value for name, cb in self._breakers.items()}


# 全局单例
circuit_breaker = CircuitBreakerRegistry()
