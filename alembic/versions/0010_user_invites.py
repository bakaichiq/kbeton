"""add user invites

Revision ID: 0010_user_invites
Revises: 0009_inv_exp_approval
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_user_invites"
down_revision = "0009_inv_exp_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    role_enum = postgresql.ENUM("Admin", "FinDir", "HeadProd", "Operator", "Warehouse", "Viewer", name="role_enum", create_type=False)
    bind = op.get_bind()
    role_enum.create(bind, checkfirst=True)

    op.create_table(
        "user_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("used_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("token", name="uq_user_invites_token"),
    )
    op.create_index("ix_user_invites_token", "user_invites", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_invites_token", table_name="user_invites")
    op.drop_table("user_invites")
