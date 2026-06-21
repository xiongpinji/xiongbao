"""可观测适配层抽象：trace / span。

抽象成最小可用接口：``trace()`` 上下文管理器产出一个 span，可记录
输入/输出/元数据。Langfuse 与 noop 实现共用此接口。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Span(Protocol):
    def set_input(self, value: Any) -> None: ...
    def set_output(self, value: Any) -> None: ...
    def set_metadata(self, **kwargs: Any) -> None: ...


@runtime_checkable
class Tracer(Protocol):
    """追踪器抽象。"""

    def trace(self, name: str, **metadata: Any):  # -> async context manager[Span]
        """开启一个 span（异步上下文管理器）。"""
        ...

    async def flush(self) -> None:
        """刷盘（关闭前调用）。"""
        ...

    async def health(self) -> bool: ...


class _NoopSpan:
    def set_input(self, value: Any) -> None:  # noqa: D102
        pass

    def set_output(self, value: Any) -> None:  # noqa: D102
        pass

    def set_metadata(self, **kwargs: Any) -> None:  # noqa: D102
        pass


class NoopTracer:
    """no-op 追踪器：未配置 Langfuse 时使用。"""

    @asynccontextmanager
    async def trace(self, name: str, **metadata: Any):
        yield _NoopSpan()

    async def flush(self) -> None:
        pass

    async def health(self) -> bool:
        return True
