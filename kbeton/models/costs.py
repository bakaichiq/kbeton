from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from kbeton.db.base import Base

class MaterialPrice(Base):
    __tablename__ = "material_prices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_key: Mapped[str] = mapped_column(String(50), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    price: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="KGS")
    valid_from: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class OverheadCost(Base):
    __tablename__ = "overhead_costs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    cost_per_m3: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="KGS")
    valid_from: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
