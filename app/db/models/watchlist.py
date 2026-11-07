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
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.security import Security
    from app.db.models.user import User


class Watchlist(Base):
    """A named set of securities owned by one user.

    Index ``ix_watchlists_user_id``
        Query: ``SELECT * FROM watchlists WHERE user_id = ?``.
        PostgreSQL does not index foreign keys automatically.
    """

    __tablename__ = "watchlists"
    __table_args__ = (Index("ix_watchlists_user_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="watchlists")
    items: Mapped[list[WatchlistItem]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
    )


class WatchlistItem(Base):
    """One security on one watchlist. The pair cannot be inserted twice."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint(
            "watchlist_id",
            "security_id",
            name="uq_watchlist_items_watchlist_security",
        ),
        Index("ix_watchlist_items_watchlist_id", "watchlist_id"),
        CheckConstraint(
            "alert_when IS NULL OR alert_when IN ('above', 'below')",
            name="ck_watchlist_items_alert_when",
        ),
        CheckConstraint(
            "target_price IS NULL OR target_price > 0",
            name="ck_watchlist_items_target_price",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    watchlist_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
    )
    security_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    alert_when: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")
    security: Mapped[Security] = relationship()
