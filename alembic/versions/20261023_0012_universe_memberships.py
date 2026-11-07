"""Market-universe membership. Securities and prices are not removed.

Revision ID: 0012_universe_memberships
Revises: 0011_research_flags
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_universe_memberships"
down_revision: str | Sequence[str] | None = "0011_research_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "universe_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("universe_code", sa.String(length=32), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "universe_code",
            "security_id",
            name="uq_universe_memberships_code_security",
        ),
    )
    op.create_index(
        "ix_universe_memberships_code_active",
        "universe_memberships",
        ["universe_code", "active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_universe_memberships_code_active",
        table_name="universe_memberships",
    )
    op.drop_table("universe_memberships")
