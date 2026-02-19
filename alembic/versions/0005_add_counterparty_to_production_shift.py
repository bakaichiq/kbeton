"""add counterparty_name to production_shifts

Revision ID: 0005_add_counterparty_to_production_shift
Revises: 0004_add_costs_and_recipe_fields
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0005_add_counterparty_to_production_shift"
down_revision = "0004_add_costs_and_recipe_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "production_shifts",
        sa.Column("counterparty_name", sa.String(length=255), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("production_shifts", "counterparty_name")
