"""add unit price and total cost to inventory txns

Revision ID: 0007_inv_cost_fields
Revises: 0006_inv_receipt_fields
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0007_inv_cost_fields"
down_revision = "0006_inv_receipt_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_txns", sa.Column("unit_price", sa.Numeric(14, 3), nullable=True))
    op.add_column("inventory_txns", sa.Column("total_cost", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory_txns", "total_cost")
    op.drop_column("inventory_txns", "unit_price")
