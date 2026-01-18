from __future__ import annotations

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kbeton.db.base import Base

class CounterpartySnapshot(Base):
    __tablename__ = "counterparty_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[Date] = mapped_column(Date, nullable=False)
    import_job_id: Mapped[int] = mapped_column(Integer, ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class CounterpartyBalance(Base):
    __tablename__ = "counterparty_balances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("counterparty_snapshots.id", ondelete="CASCADE"), nullable=False)

    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    counterparty_name_norm: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    receivable_money: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    receivable_assets: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payable_money: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    payable_assets: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ending_balance_money: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

Index("ix_cp_balance_snapshot_norm", CounterpartyBalance.snapshot_id, CounterpartyBalance.counterparty_name_norm)
