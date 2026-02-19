from __future__ import annotations

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kbeton.db.base import Base
from kbeton.models.enums import ShiftType, ShiftStatus, ProductType

class ProductionShift(Base):
    __tablename__ = "production_shifts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operator_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False)
    shift_type: Mapped[ShiftType] = mapped_column(Enum(ShiftType, name="shift_type_enum"), nullable=False)
    equipment: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    area: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[ShiftStatus] = mapped_column(Enum(ShiftStatus, name="shift_status_enum"), nullable=False, default=ShiftStatus.draft)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")

    submitted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    outputs = relationship("ProductionOutput", back_populates="shift", cascade="all, delete-orphan")

class ProductionOutput(Base):
    __tablename__ = "production_outputs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shift_id: Mapped[int] = mapped_column(Integer, ForeignKey("production_shifts.id", ondelete="CASCADE"), nullable=False)
    product_type: Mapped[ProductType] = mapped_column(Enum(ProductType, name="product_type_enum"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    uom: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    mark: Mapped[str] = mapped_column(String(50), nullable=False, default="")  # for concrete

    shift = relationship("ProductionShift", back_populates="outputs")
