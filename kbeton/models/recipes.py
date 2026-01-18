from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from kbeton.db.base import Base

class ConcreteRecipe(Base):
    __tablename__ = "concrete_recipes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mark: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    cement_kg: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    sand_t: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    crushed_stone_t: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    screening_t: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    water_l: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    additives_l: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
