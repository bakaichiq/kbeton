"""add costs and recipe fields

Revision ID: 0004_add_costs_and_recipe_fields
Revises: 0003_add_concrete_recipes
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0004_add_costs_and_recipe_fields"
down_revision = "0003_add_concrete_recipes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("concrete_recipes", sa.Column("water_l", sa.Numeric(10, 3), nullable=False, server_default="0"))
    op.add_column("concrete_recipes", sa.Column("additives_l", sa.Numeric(10, 3), nullable=False, server_default="0"))

    op.create_table(
        "material_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_key", sa.String(length=50), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("price", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KGS"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_material_prices_item_validfrom", "material_prices", ["item_key", "valid_from"])

    op.create_table(
        "overhead_costs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("cost_per_m3", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KGS"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_overhead_costs_name_validfrom", "overhead_costs", ["name", "valid_from"])


def downgrade() -> None:
    op.drop_index("ix_overhead_costs_name_validfrom", table_name="overhead_costs")
    op.drop_table("overhead_costs")
    op.drop_index("ix_material_prices_item_validfrom", table_name="material_prices")
    op.drop_table("material_prices")
    op.drop_column("concrete_recipes", "additives_l")
    op.drop_column("concrete_recipes", "water_l")
