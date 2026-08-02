"""计费 ORM：订阅 + 账单明细。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from xagent.infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SubscriptionORM(Base):
    __tablename__ = "subscriptions"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan: Mapped[str] = mapped_column(String(32), default="free")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TenantUsageORM(Base):
    """租户用量计数（配额扣减）。与 billing_records（账单流水）分离：
    运行前配额扣减写本表；运行后结算（真实 tokens）仅写流水，避免重复计数。"""

    __tablename__ = "tenant_usage"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_runs: Mapped[int] = mapped_column(Integer, default=0)
    media_generations: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)


class BillingRecordORM(Base):
    __tablename__ = "billing_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64), default="")
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    detail: Mapped[str] = mapped_column(String(1024), default="")  # JSON
