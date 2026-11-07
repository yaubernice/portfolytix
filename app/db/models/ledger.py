from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.portfolio import Portfolio
    from app.db.models.security import Security


class CashMovement(Base):
    """Cash entering or leaving a portfolio. A dividend is income, not a share fill.

    ``fx_rate`` is USD per one unit of ``currency``, stored with the movement.
    A non-USD row without a rate is kept and left out of the dollar total.
    """

    __tablename__ = "cash_movements"
    __table_args__ = (
        Index("ix_cash_movements_portfolio_id_timestamp", "portfolio_id", "timestamp"),
        CheckConstraint(
            "kind IN ('deposit', 'withdrawal', 'dividend')",
            name="ck_cash_movements_kind",
        ),
        CheckConstraint("amount > 0", name="ck_cash_movements_amount"),
        CheckConstraint(
            "fx_rate IS NULL OR fx_rate > 0",
            name="ck_cash_movements_fx_rate",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    portfolio_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    security_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("securities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    portfolio: Mapped[Portfolio] = relationship()
    security: Mapped[Security | None] = relationship()


class ShareSplit(Base):
    """A split applied to shares already held. 2-for-1 is numerator 2, denominator 1."""

    __tablename__ = "share_splits"
    __table_args__ = (
        Index("ix_share_splits_portfolio_id_timestamp", "portfolio_id", "timestamp"),
        CheckConstraint("numerator > 0", name="ck_share_splits_numerator"),
        CheckConstraint("denominator > 0", name="ck_share_splits_denominator"),
        CheckConstraint(
            "numerator <> denominator",
            name="ck_share_splits_changes_shares",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    portfolio_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    security_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("securities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    numerator: Mapped[int] = mapped_column(Integer, nullable=False)
    denominator: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    portfolio: Mapped[Portfolio] = relationship()
    security: Mapped[Security] = relationship()
