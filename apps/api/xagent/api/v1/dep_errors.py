"""依赖不可用 → 诚实 503 的统一处理。

向量库本地锁冲突抛 ``RuntimeError``，远程连接失败抛
``ConnectionError`` / ``TimeoutError`` / ``OSError``。这些属于「依赖服务
暂时不可用」，不应泄成 500 + traceback，统一转换为 503 + 明确 detail。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

# 依赖不可用异常类型：qdrant 本地锁冲突（RuntimeError）、远程连接失败等
DEP_UNAVAILABLE_ERRORS = (RuntimeError, ConnectionError, TimeoutError, OSError)


@contextmanager
def dependency_guard(dep_name: str = "向量存储") -> Iterator[None]:
    """把依赖不可用异常转换为 503（而非 500 + traceback）。

    用法::

        with dependency_guard():
            store = get_vector_store()
            await store.upsert(records)
    """
    try:
        yield
    except DEP_UNAVAILABLE_ERRORS as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"依赖服务不可用：{dep_name}暂时不可用"
                f"（{type(exc).__name__}: {exc}）"
            ),
        ) from exc
