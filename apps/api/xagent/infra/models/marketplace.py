"""插件/技能市场 ORM：市场条目持久化。"""

from __future__ import annotations

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base


class MarketEntryORM(Base):
    __tablename__ = "marketplace_entries"

    entry_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    author: Mapped[str] = mapped_column(String(64), default="")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    tags: Mapped[str] = mapped_column(String(512), default="")  # JSON list
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    skill_id: Mapped[str] = mapped_column(String(64), default="")
    published_at: Mapped[float] = mapped_column(Float, default=0.0)  # epoch 秒
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)  # epoch 秒
    status: Mapped[str] = mapped_column(String(16), default="published")
