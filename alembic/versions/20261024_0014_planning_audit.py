"""Paper books, goals, journal, fund constituents, share links, and voided fills.

Revision ID: 0014_planning_audit
Revises: 0013_cash_splits_alerts
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_planning_audit"
down_revision: str | Sequence[str] | None = "0013_cash_splits_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portfolios",
        sa.Column(
            "is_paper",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "transactions",
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("corrects_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_corrects_id",
        "transactions",
        "transactions",
        ["corrects_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "fundamentals",
        sa.Column("expense_ratio", sa.Numeric(precision=18, scale=8), nullable=True),
    )
    op.create_table(
        "goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("target_amount", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column(
            "monthly_contribution",
            sa.Numeric(precision=20, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "etf_holdings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("etf_security_id", sa.Uuid(), nullable=False),
        sa.Column("constituent_ticker", sa.String(length=16), nullable=False),
        sa.Column("weight", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["etf_security_id"],
            ["securities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "share_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("share_links")
    op.drop_table("etf_holdings")
    op.drop_table("journal_entries")
    op.drop_table("goals")
    op.drop_column("fundamentals", "expense_ratio")
    op.drop_constraint(
        "fk_transactions_corrects_id",
        "transactions",
        type_="foreignkey",
    )
    op.drop_column("transactions", "corrects_id")
    op.drop_column("transactions", "voided_at")
    op.drop_column("portfolios", "is_paper")
