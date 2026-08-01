"""请求重试：下游调用自动重试与退避。

功能：
- 指数退避 + 抖动
- 可配置重试条件（状态码/异常类型）
- 最大重试次数
- 重试预算（防止雪崩）

用法：
    from xagent.api.request_retry import retry, RetryConfig

    config = RetryConfig(max_retries=3, backoff_base=0.5)
    result = await retry(call_downstream, config=config)
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from xagent.infra.logging import get_logger

logger = get_logger("xagent.retry")


@dataclass
class RetryConfig:
    """重试配置。"""

    max_retries: int = 3
    backoff_base: float = 0.5  # 基础退避（秒）
    backoff_max: float = 30.0  # 最大退避
    jitter: bool = True  # 是否添加随机抖动
    retryable_statuses: set[int] = field(default_factory=lambda: {502, 503, 504, 429})
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    # 重试预算：窗口内最多重试次数
    budget_window_s: float = 60.0
    budget_max_retries: int = 100


@dataclass
class RetryState:
    """重试状态跟踪。"""

    attempts: int = 0
    last_error: Exception | None = None
    total_wait_s: float = 0.0
    start_time: float = field(default_factory=time.time)


class RetryBudget:
    """重试预算：防止重试风暴。"""

    def __init__(self, window_s: float = 60.0, max_retries: int = 100):
        self._window_s = window_s
        self._max = max_retries
        self._timestamps: list[float] = []

    def allow(self) -> bool:
        """是否允许重试。"""
        now = time.time()
        cutoff = now - self._window_s
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        if len(self._timestamps) >= self._max:
            return False
        self._timestamps.append(now)
        return True

    @property
    def remaining(self) -> int:
        now = time.time()
        cutoff = now - self._window_s
        active = [t for t in self._timestamps if t > cutoff]
        return max(0, self._max - len(active))


# 全局重试预算
_global_budget = RetryBudget()


def _compute_delay(attempt: int, config: RetryConfig) -> float:
    """计算退避延迟。"""
    delay = min(config.backoff_base * (2 ** attempt), config.backoff_max)
    if config.jitter:
        delay = delay * (0.5 + random.random() * 0.5)
    return delay


async def retry(
    fn: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    config: RetryConfig | None = None,
    budget: RetryBudget | None = None,
    on_retry: Callable[[RetryState], None] | None = None,
    **kwargs: Any,
) -> Any:
    """执行带重试的异步调用。

    Args:
        fn: 异步函数
        config: 重试配置
        budget: 重试预算（默认全局）
        on_retry: 重试回调

    Returns:
        函数返回值

    Raises:
        最后一次异常（重试耗尽后）
    """
    cfg = config or RetryConfig()
    bgt = budget or _global_budget
    state = RetryState()

    while True:
        try:
            state.attempts += 1
            return await fn(*args, **kwargs)
        except cfg.retryable_exceptions as exc:
            state.last_error = exc

            if state.attempts > cfg.max_retries:
                logger.warning(
                    "retry exhausted: %d attempts, last_error=%s",
                    state.attempts, exc,
                )
                raise

            if not bgt.allow():
                logger.warning("retry budget exhausted, not retrying")
                raise

            delay = _compute_delay(state.attempts - 1, cfg)
            state.total_wait_s += delay
            logger.info(
                "retry %d/%d after %.2fs: %s",
                state.attempts, cfg.max_retries, delay, exc,
            )
            on_retry?.(state)
            await asyncio.sleep(delay)


class RetryableResponse(Exception):
    """可重试的 HTTP 响应。"""

    def __init__(self, status_code: int, body: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}")


async def retry_http(
    fn: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    config: RetryConfig | None = None,
    **kwargs: Any,
) -> Any:
    """HTTP 请求重试（根据状态码判断）。"""
    cfg = config or RetryConfig()
    state = RetryState()

    while True:
        state.attempts += 1
        try:
            response = await fn(*args, **kwargs)
            status = getattr(response, "status_code", 200)
            if status not in cfg.retryable_statuses:
                return response
            raise RetryableResponse(status)
        except RetryableResponse as exc:
            if state.attempts > cfg.max_retries:
                raise
            if not _global_budget.allow():
                raise
            delay = _compute_delay(state.attempts - 1, cfg)
            state.total_wait_s += delay
            logger.info("http retry %d/%d: status=%d", state.attempts, cfg.max_retries, exc.status_code)
            await asyncio.sleep(delay)
