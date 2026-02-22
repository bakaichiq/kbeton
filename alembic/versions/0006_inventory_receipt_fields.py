"""add inventory receipt fields and enum value

Revision ID: 0006_inv_receipt_fields
Revises: 0005_add_counterparty_shift
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0006_inv_receipt_fields"
down_revision = "0005_add_counterparty_shift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE inv_txn_type_enum ADD VALUE IF NOT EXISTS 'receipt'")
    op.add_column("inventory_txns", sa.Column("fact_weight", sa.Numeric(14, 3), nullable=True))
    op.add_column(
        "inventory_txns",
        sa.Column("invoice_photo_s3_key", sa.String(length=512), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("inventory_txns", "invoice_photo_s3_key")
    op.drop_column("inventory_txns", "fact_weight")
    # PostgreSQL enums do not support dropping values safely in-place.
