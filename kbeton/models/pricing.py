from __future__ import annotations

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from kbeton.db.base import Base
from kbeton.models.enums import PriceKind

class PriceVersion(Base):
    __tablename__ = "price_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[PriceKind] = mapped_column(Enum(PriceKind, name="price_kind_enum"), nullable=False)
    item_key: Mapped[str] = mapped_column(String(50), nullable=False)  # concrete mark e.g. M300 or 'blocks'
    price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="KGS")
    valid_from: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

Index("ix_price_kind_item_validfrom", PriceVersion.kind, PriceVersion.item_key, PriceVersion.valid_from.desc())
