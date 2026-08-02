"""同步 DB 会话：供同步域服务（billing / audit / marketplace）写透持久化。

背景：billing service、AuditLog 等对调用方暴露同步接口（路由/测试同步调用），
无法直接 await 异步引擎。这里用同步驱动（aiosqlite→sqlite、asyncpg→psycopg）
派生独立引擎，按 URL 缓存，供这些同步服务做读写。

- 引擎首次创建时 ``Base.metadata.create_all``（幂等 checkfirst），保证 lite/SQLite
  及测试环境（lifespan 未跑 create_all 时）表存在；生产仍应走 alembic 迁移。
- DB 不可用时调用方自行捕获异常并降级（内存实现）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from xagent.infra.logging import get_logger
from xagent.infra.settings import get_settings

logger = get_logger("xagent.repos.sync_db")

_engines: dict[str, Engine] = {}


def _sync_url(url: str) -> str:
    """异步驱动 URL 转同步驱动（与 migrations/env.py 规则一致）。"""
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        .replace("sqlite+aiosqlite://", "sqlite://")
    )


def get_sync_engine() -> Engine:
    """按当前 settings 的 DB URL 取（或建）同步引擎。"""
    url = _sync_url(get_settings().db.url)
    engine = _engines.get(url)
    if engine is None:
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            # 允许跨线程使用（FastAPI 线程池 / 测试）
            kwargs["connect_args"] = {"check_same_thread": False}
        engine = create_engine(url, **kwargs)
        # 幂等建表：lite/测试兜底；生产由 alembic 管理（create_all 不覆盖已有表）
        import xagent.infra.models  # noqa: F401  注册全部 ORM

        from xagent.infra.db import Base

        Base.metadata.create_all(engine)
        _engines[url] = engine
    return engine


@contextmanager
def sync_session() -> Iterator[Session]:
    """同步会话上下文：正常结束 commit，异常 rollback 并抛出。"""
    session = Session(get_sync_engine(), expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_sync_engines() -> None:
    """释放全部缓存引擎（测试环境切换 DB URL 后调用）。"""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
