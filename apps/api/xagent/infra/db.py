"""数据库：SQLAlchemy 2.0 异步引擎 + session 工厂。

- lite 模式默认 SQLite（aiosqlite），full 模式 Postgres（asyncpg）。
- ``Base`` 为所有 ORM 模型的声明基类。
- ``get_session()`` 为 FastAPI 依赖，产出 ``AsyncSession``。
- ``ping()`` 供健康探针检测连通性。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from xagent.infra.settings import get_settings


class Base(DeclarativeBase):
    """ORM 声明基类。所有模型继承它。"""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """惰性创建全局异步引擎。"""
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs: dict = {"echo": settings.db.echo, "future": True}
        # SQLite 不支持连接池大小参数
        if not settings.db.url.startswith("sqlite"):
            kwargs.update(
                pool_size=settings.db.pool_size,
                max_overflow=settings.db.max_overflow,
                pool_pre_ping=True,
            )
        _engine = create_async_engine(settings.db.url, **kwargs)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：产出一个 AsyncSession，结束自动关闭。"""
    async with get_sessionmaker()() as session:
        yield session


async def ping() -> bool:
    """探活：执行 SELECT 1。"""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    """关闭引擎（应用 shutdown 调用）。"""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
