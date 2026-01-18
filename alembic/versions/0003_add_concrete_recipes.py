"""add concrete recipes

Revision ID: 0003_add_concrete_recipes
Revises: 0002_add_sand_product_type
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0003_add_concrete_recipes"
down_revision = "0002_add_sand_product_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concrete_recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mark", sa.String(length=50), nullable=False),
        sa.Column("cement_kg", sa.Numeric(10, 3), nullable=False, server_default="0"),
        sa.Column("sand_t", sa.Numeric(10, 3), nullable=False, server_default="0"),
        sa.Column("crushed_stone_t", sa.Numeric(10, 3), nullable=False, server_default="0"),
        sa.Column("screening_t", sa.Numeric(10, 3), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("mark", name="uq_concrete_recipes_mark"),
    )


def downgrade() -> None:
    op.drop_table("concrete_recipes")
