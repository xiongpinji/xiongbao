"""Alembic env。URL 从 XAGENT_DB__URL 注入；同步引擎用于迁移。"""

from __future__ import annotations

import os
from logging.config import fileConfig

import xagent.infra.models  # noqa: F401  注册所有模型到 metadata
from alembic import context
from sqlalchemy import engine_from_config, pool
from xagent.infra.db import Base


# 把 alembic 的 DB URL 转成同步驱动（asyncpg->psycopg / aiosqlite->sqlite）
def _sync_url(url: str) -> str:
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        .replace("sqlite+aiosqlite://", "sqlite://")
    )

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 注入 URL
db_url = os.environ.get("XAGENT_DB__URL") or "sqlite:///./xagent.db"
config.set_main_option("sqlalchemy.url", _sync_url(db_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
