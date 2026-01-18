from __future__ import annotations

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kbeton.db.base import Base
from kbeton.models.enums import TxType, PatternType

class FinanceArticle(Base):
    __tablename__ = "finance_articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[TxType] = mapped_column(Enum(TxType, name="tx_type_enum"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class MappingRule(Base):
    __tablename__ = "mapping_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[TxType] = mapped_column(Enum(TxType, name="rule_kind_enum"), nullable=False)
    pattern_type: Mapped[PatternType] = mapped_column(Enum(PatternType, name="pattern_type_enum"), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("finance_articles.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    article = relationship("FinanceArticle")

class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # finance|counterparty
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class FinanceTransaction(Base):
    __tablename__ = "finance_transactions"
    __table_args__ = (
        UniqueConstraint("import_job_id", "dedup_hash", name="uq_fin_txn_import_dedup"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_job_id: Mapped[int] = mapped_column(Integer, ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False)

    date: Mapped[Date] = mapped_column(Date, nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="KGS")
    tx_type: Mapped[TxType] = mapped_column(Enum(TxType, name="txn_type_enum"), nullable=False, default=TxType.unknown)

    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    counterparty: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    income_article_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("finance_articles.id", ondelete="SET NULL"), nullable=True)
    expense_article_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("finance_articles.id", ondelete="SET NULL"), nullable=True)

    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
