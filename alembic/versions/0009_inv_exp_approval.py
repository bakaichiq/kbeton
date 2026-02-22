"""inventory receipt expense approval linkage

Revision ID: 0009_inv_exp_approval
Revises: 0008_prod_realz
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa

revision = "0009_inv_exp_approval"
down_revision = "0008_prod_realz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_txns", sa.Column("finance_approval_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("inventory_txns", sa.Column("finance_txn_id", sa.Integer(), nullable=True))
    op.add_column("inventory_txns", sa.Column("expense_approved_by_user_id", sa.Integer(), nullable=True))
    op.add_column("inventory_txns", sa.Column("expense_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_inventory_txns_finance_txn_id",
        "inventory_txns",
        "finance_transactions",
        ["finance_txn_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_inventory_txns_expense_approved_by_user_id",
        "inventory_txns",
        "users",
        ["expense_approved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("inventory_txns", "finance_approval_required", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_inventory_txns_expense_approved_by_user_id", "inventory_txns", type_="foreignkey")
    op.drop_constraint("fk_inventory_txns_finance_txn_id", "inventory_txns", type_="foreignkey")
    op.drop_column("inventory_txns", "finance_approval_required")
    op.drop_column("inventory_txns", "expense_approved_at")
    op.drop_column("inventory_txns", "expense_approved_by_user_id")
    op.drop_column("inventory_txns", "finance_txn_id")
