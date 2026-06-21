"""结构化日志：基于 structlog，输出 JSON（生产）或彩色控制台（开发）。

提供 ``configure_logging()`` 在应用启动时调用一次，``get_logger(name)`` 取 logger。
日志带 request_id 上下文（由中间件注入）。
"""

from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def configure_logging(debug: bool = False) -> None:
    """配置 structlog + 标准库 logging。幂等。"""
    global _configured
    if _configured:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if debug else logging.INFO,
    )

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if debug:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "xagent") -> structlog.stdlib.BoundLogger:
    """取一个绑定 logger。"""
    return structlog.get_logger(name)


def bind_request_context(request_id: str, **kwargs: str) -> None:
    """把 request_id 等绑定到当前上下文（中间件调用）。"""
    structlog.contextvars.bind_contextvars(request_id=request_id, **kwargs)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
