from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func, Enum
from sqlalchemy.orm import Mapped, mapped_column

from kbeton.db.base import Base
from kbeton.models.enums import InventoryTxnType

class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    uom: Mapped[str] = mapped_column(String(20), nullable=False, default="шт")
    min_qty: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), primary_key=True)
    qty: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class InventoryTxn(Base):
    __tablename__ = "inventory_txns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)
    txn_type: Mapped[InventoryTxnType] = mapped_column(Enum(InventoryTxnType, name="inv_txn_type_enum"), nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)
    total_cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    receiver: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    department: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    fact_weight: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)
    invoice_photo_s3_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    finance_approval_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    finance_txn_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("finance_transactions.id", ondelete="SET NULL"), nullable=True)
    expense_approved_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expense_approved_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
