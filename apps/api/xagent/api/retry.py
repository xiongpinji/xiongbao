"""请求重试机制：指数退避 + 抖动。

对下游调用（LLM / HTTP / DB）自动重试：
- 可配置最大重试次数
- 指数退避：delay = base * (2 ^ attempt) + jitter
- 可配置可重试异常/状态码
- 重试事件回调（日志 / 指标）

用法：
    from xagent.api.retry import retry_async, RetryConfig

    @retry_async(RetryConfig(max_retries=3, base_delay=1.0))
    async def call_llm(prompt):
        ...
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Type

from xagent.infra.logging import get_logger

logger = get_logger("xagent.retry")


@dataclass
class RetryConfig:
    """重试配置。"""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: bool = True
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,)
    on_retry: Callable[[int, Exception, float], None] | None = None


def compute_delay(attempt: int, config: RetryConfig) -> float:
    """计算第 N 次重试的等待时间。"""
    delay = config.base_delay * (2 ** attempt)
    delay = min(delay, config.max_delay)
    if config.jitter:
        delay += random.uniform(0, delay * 0.1)
    return delay


def retry_async(config: RetryConfig | None = None):
    """异步重试装饰器。"""
    cfg = config or RetryConfig()

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None

            for attempt in range(cfg.max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except cfg.retryable_exceptions as e:
                    last_exc = e

                    if attempt >= cfg.max_retries:
                        logger.error(
                            "retry_exhausted",
                            fn=fn.__name__,
                            attempts=attempt + 1,
                            error=str(e)[:200],
                        )
                        raise

                    delay = compute_delay(attempt, cfg)
                    logger.warning(
                        "retry_attempt",
                        fn=fn.__name__,
                        attempt=attempt + 1,
                        delay_s=round(delay, 2),
                        error=str(e)[:100],
                    )

                    if cfg.on_retry:
                        cfg.on_retry(attempt + 1, e, delay)

                    await asyncio.sleep(delay)

            raise last_exc  # type: ignore

        return wrapper

    return decorator


class RetryableHTTPError(Exception):
    """可重试的 HTTP 错误。"""

    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


# 预置配置
LLM_RETRY = RetryConfig(
    max_retries=3,
    base_delay=2.0,
    max_delay=30.0,
    retryable_exceptions=(TimeoutError, ConnectionError, RetryableHTTPError),
)

DB_RETRY = RetryConfig(
    max_retries=2,
    base_delay=0.5,
    max_delay=5.0,
    retryable_exceptions=(ConnectionError, TimeoutError),
)
