"""add sand product type

Revision ID: 0002_add_sand_product_type
Revises: 0001_init
Create Date: 2026-01-08

"""
from alembic import op

revision = "0002_add_sand_product_type"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE product_type_enum ADD VALUE IF NOT EXISTS 'sand'")


def downgrade() -> None:
    # Enum value removals are not safe in Postgres; keep for backward compatibility.
    pass
