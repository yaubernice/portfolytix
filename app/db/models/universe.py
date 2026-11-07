"""Membership of a named market universe. Not a portfolio and not a price."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.security import Security


class UniverseMembership(Base):
    """One security's place in a maintained list such as the S&P 500 file.

    Leaving the list sets ``active`` false. The security row and its
    prices stay. This table does not store users, trades, or bars.
    """

    __tablename__ = "universe_memberships"
    __table_args__ = (
        UniqueConstraint(
            "universe_code",
            "security_id",
            name="uq_universe_memberships_code_security",
        ),
        Index(
            "ix_universe_memberships_code_active",
            "universe_code",
            "active",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    universe_code: Mapped[str] = mapped_column(String(32), nullable=False)
    security_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    security: Mapped[Security] = relationship()
