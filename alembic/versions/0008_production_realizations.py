"""add production realizations

Revision ID: 0008_prod_realz
Revises: 0007_inv_cost_fields
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0008_prod_realz"
down_revision = "0007_inv_cost_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_realizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("output_id", sa.Integer(), sa.ForeignKey("production_outputs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("realized_qty", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("finance_txn_id", sa.Integer(), sa.ForeignKey("finance_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_prod_real_output_id", "production_realizations", ["output_id"])


def downgrade() -> None:
    op.drop_index("ix_prod_real_output_id", table_name="production_realizations")
    op.drop_table("production_realizations")
