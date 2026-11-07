"""Cash movements, share splits, and watchlist price targets.

Revision ID: 0013_cash_splits_alerts
Revises: 0012_universe_memberships
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_cash_splits_alerts"
down_revision: str | Sequence[str] | None = "0012_universe_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cash_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("security_id", sa.Uuid(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('deposit', 'withdrawal', 'dividend')",
            name="ck_cash_movements_kind",
        ),
        sa.CheckConstraint("amount > 0", name="ck_cash_movements_amount"),
        sa.CheckConstraint(
            "fx_rate IS NULL OR fx_rate > 0",
            name="ck_cash_movements_fx_rate",
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["security_id"], ["securities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cash_movements_portfolio_id_timestamp",
        "cash_movements",
        ["portfolio_id", "timestamp"],
    )
    op.create_table(
        "share_splits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("numerator", sa.Integer(), nullable=False),
        sa.Column("denominator", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("numerator > 0", name="ck_share_splits_numerator"),
        sa.CheckConstraint("denominator > 0", name="ck_share_splits_denominator"),
        sa.CheckConstraint(
            "numerator <> denominator",
            name="ck_share_splits_changes_shares",
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["security_id"], ["securities.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_share_splits_portfolio_id_timestamp",
        "share_splits",
        ["portfolio_id", "timestamp"],
    )
    op.add_column(
        "watchlist_items",
        sa.Column("target_price", sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column(
        "watchlist_items",
        sa.Column("alert_when", sa.String(length=8), nullable=True),
    )
    op.create_check_constraint(
        "ck_watchlist_items_alert_when",
        "watchlist_items",
        "alert_when IS NULL OR alert_when IN ('above', 'below')",
    )
    op.create_check_constraint(
        "ck_watchlist_items_target_price",
        "watchlist_items",
        "target_price IS NULL OR target_price > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_watchlist_items_target_price", "watchlist_items", type_="check")
    op.drop_constraint("ck_watchlist_items_alert_when", "watchlist_items", type_="check")
    op.drop_column("watchlist_items", "alert_when")
    op.drop_column("watchlist_items", "target_price")
    op.drop_index("ix_share_splits_portfolio_id_timestamp", table_name="share_splits")
    op.drop_table("share_splits")
    op.drop_index(
        "ix_cash_movements_portfolio_id_timestamp",
        table_name="cash_movements",
    )
    op.drop_table("cash_movements")
