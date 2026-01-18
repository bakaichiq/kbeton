"""init

Revision ID: 0001_init
Revises: 
Create Date: 2026-01-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Enums
    role_enum = postgresql.ENUM("Admin","FinDir","HeadProd","Operator","Warehouse","Viewer", name="role_enum", create_type=False)
    tx_type_enum = postgresql.ENUM("income","expense","unknown", name="tx_type_enum", create_type=False)
    rule_kind_enum = postgresql.ENUM("income","expense","unknown", name="rule_kind_enum", create_type=False)
    pattern_type_enum = postgresql.ENUM("contains","regex", name="pattern_type_enum", create_type=False)
    txn_type_enum = postgresql.ENUM("income","expense","unknown", name="txn_type_enum", create_type=False)
    price_kind_enum = postgresql.ENUM("concrete","blocks", name="price_kind_enum", create_type=False)
    shift_type_enum = postgresql.ENUM("day","night", name="shift_type_enum", create_type=False)
    shift_status_enum = postgresql.ENUM("draft","submitted","approved","rejected", name="shift_status_enum", create_type=False)
    product_type_enum = postgresql.ENUM("crushed_stone","screening","concrete","blocks", name="product_type_enum", create_type=False)
    inv_txn_type_enum = postgresql.ENUM("issue","writeoff","adjustment", name="inv_txn_type_enum", create_type=False)

    bind = op.get_bind()
    role_enum.create(bind, checkfirst=True)
    tx_type_enum.create(bind, checkfirst=True)
    rule_kind_enum.create(bind, checkfirst=True)
    pattern_type_enum.create(bind, checkfirst=True)
    txn_type_enum.create(bind, checkfirst=True)
    price_kind_enum.create(bind, checkfirst=True)
    shift_type_enum.create(bind, checkfirst=True)
    shift_status_enum.create(bind, checkfirst=True)
    product_type_enum.create(bind, checkfirst=True)
    inv_txn_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("role", role_enum, nullable=False, server_default="Viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_tg_id", "users", ["tg_id"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("entity_id", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "finance_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", tx_type_enum, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", name="uq_finance_articles_name"),
    )

    op.create_table(
        "mapping_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", rule_kind_enum, nullable=False),
        sa.Column("pattern_type", pattern_type_enum, nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("finance_articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("s3_key", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "finance_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(14,2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KGS"),
        sa.Column("tx_type", txn_type_enum, nullable=False, server_default="unknown"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("counterparty", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("income_article_id", sa.Integer(), sa.ForeignKey("finance_articles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expense_article_id", sa.Integer(), sa.ForeignKey("finance_articles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dedup_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("import_job_id", "dedup_hash", name="uq_fin_txn_import_dedup"),
    )
    op.create_index("ix_finance_transactions_date", "finance_transactions", ["date"])

    op.create_table(
        "price_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", price_kind_enum, nullable=False),
        sa.Column("item_key", sa.String(length=50), nullable=False),
        sa.Column("price", sa.Numeric(14,2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KGS"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_price_kind_item_validfrom", "price_versions", ["kind","item_key","valid_from"])

    op.create_table(
        "production_shifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operator_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("shift_type", shift_type_enum, nullable=False),
        sa.Column("equipment", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("area", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", shift_status_enum, nullable=False, server_default="draft"),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "production_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shift_id", sa.Integer(), sa.ForeignKey("production_shifts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_type", product_type_enum, nullable=False),
        sa.Column("quantity", sa.Numeric(14,3), nullable=False, server_default="0"),
        sa.Column("uom", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("mark", sa.String(length=50), nullable=False, server_default=""),
    )

    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=False, server_default="шт"),
        sa.Column("min_qty", sa.Numeric(14,3), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", name="uq_inventory_items_name"),
    )

    op.create_table(
        "inventory_balances",
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("qty", sa.Numeric(14,3), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "inventory_txns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("txn_type", inv_txn_type_enum, nullable=False),
        sa.Column("qty", sa.Numeric(14,3), nullable=False),
        sa.Column("receiver", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("department", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "counterparty_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "counterparty_balances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("counterparty_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counterparty_name", sa.String(length=255), nullable=False),
        sa.Column("counterparty_name_norm", sa.String(length=255), nullable=False),
        sa.Column("receivable_money", sa.Numeric(14,2), nullable=False, server_default="0"),
        sa.Column("receivable_assets", sa.Text(), nullable=False, server_default=""),
        sa.Column("payable_money", sa.Numeric(14,2), nullable=False, server_default="0"),
        sa.Column("payable_assets", sa.Text(), nullable=False, server_default=""),
        sa.Column("ending_balance_money", sa.Numeric(14,2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_counterparty_balances_counterparty_name_norm", "counterparty_balances", ["counterparty_name_norm"])
    op.create_index("ix_cp_balance_snapshot_norm", "counterparty_balances", ["snapshot_id","counterparty_name_norm"])

def downgrade() -> None:
    op.drop_index("ix_cp_balance_snapshot_norm", table_name="counterparty_balances")
    op.drop_index("ix_counterparty_balances_counterparty_name_norm", table_name="counterparty_balances")
    op.drop_table("counterparty_balances")
    op.drop_table("counterparty_snapshots")
    op.drop_table("inventory_txns")
    op.drop_table("inventory_balances")
    op.drop_table("inventory_items")
    op.drop_table("production_outputs")
    op.drop_table("production_shifts")
    op.drop_index("ix_price_kind_item_validfrom", table_name="price_versions")
    op.drop_table("price_versions")
    op.drop_index("ix_finance_transactions_date", table_name="finance_transactions")
    op.drop_table("finance_transactions")
    op.drop_table("import_jobs")
    op.drop_table("mapping_rules")
    op.drop_table("finance_articles")
    op.drop_table("audit_logs")
    op.drop_index("ix_users_tg_id", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    sa.Enum(name="inv_txn_type_enum").drop(bind, checkfirst=True)
    sa.Enum(name="product_type_enum").drop(bind, checkfirst=True)
    sa.Enum(name="shift_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="shift_type_enum").drop(bind, checkfirst=True)
    sa.Enum(name="price_kind_enum").drop(bind, checkfirst=True)
    sa.Enum(name="txn_type_enum").drop(bind, checkfirst=True)
    sa.Enum(name="pattern_type_enum").drop(bind, checkfirst=True)
    sa.Enum(name="rule_kind_enum").drop(bind, checkfirst=True)
    sa.Enum(name="tx_type_enum").drop(bind, checkfirst=True)
    sa.Enum(name="role_enum").drop(bind, checkfirst=True)
