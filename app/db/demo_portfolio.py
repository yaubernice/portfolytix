"""Labelled demo account. Sample fills only; no simulated market prices.

The fills belong to the demo account's own portfolio. An existing account
that already has a different portfolio is left unchanged. Re-running the
seed does not insert a second copy of the same fill. Daily bars stay the
job of market-data ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Portfolio, Price, Security, Transaction, User
from app.repositories.security_repository import SecurityRepository

DEMO_EMAIL = "demo-book@example.com"
DEMO_BOOK_MARK = "Labelled demo book."
DEMO_PORTFOLIO_NAME = "Demo portfolio"
DEMO_PORTFOLIO_DESCRIPTION = (
    "Labelled demo book. These fills are sample trades for this demo "
    "account, not a brokerage import. Market prices are not invented here."
)


@dataclass(frozen=True)
class _Fill:
    ticker: str
    name: str
    sector: str
    quantity: Decimal
    price: Decimal
    timestamp: datetime


# Cost-basis fills. These numbers are the sample trade price, not a quote.
# Dates span more than six months so a stored daily history can draw a line.
_FILLS: tuple[_Fill, ...] = (
    _Fill(
        "AAPL",
        "Apple Inc.",
        "Technology",
        Decimal("8"),
        Decimal("180"),
        datetime(2026, 4, 2, 15, 0, tzinfo=UTC),
    ),
    _Fill(
        "MSFT",
        "Microsoft Corporation",
        "Technology",
        Decimal("4"),
        Decimal("380"),
        datetime(2026, 4, 16, 15, 0, tzinfo=UTC),
    ),
    _Fill(
        "JNJ",
        "Johnson & Johnson",
        "Healthcare",
        Decimal("6"),
        Decimal("155"),
        datetime(2026, 5, 7, 15, 0, tzinfo=UTC),
    ),
    _Fill(
        "JPM",
        "JPMorgan Chase & Co.",
        "Financial Services",
        Decimal("5"),
        Decimal("190"),
        datetime(2026, 5, 21, 15, 0, tzinfo=UTC),
    ),
    _Fill(
        "XOM",
        "Exxon Mobil Corporation",
        "Energy",
        Decimal("7"),
        Decimal("110"),
        datetime(2026, 6, 11, 15, 0, tzinfo=UTC),
    ),
    _Fill(
        "CAT",
        "Caterpillar Inc.",
        "Industrials",
        Decimal("2"),
        Decimal("330"),
        datetime(2026, 7, 9, 15, 0, tzinfo=UTC),
    ),
    _Fill(
        "GOOGL",
        "Alphabet Inc. Class A",
        "Communication Services",
        Decimal("3"),
        Decimal("170"),
        datetime(2026, 8, 6, 15, 0, tzinfo=UTC),
    ),
    _Fill(
        "NEE",
        "NextEra Energy Inc.",
        "Utilities",
        Decimal("4"),
        Decimal("70"),
        datetime(2026, 9, 3, 15, 0, tzinfo=UTC),
    ),
)


@dataclass(frozen=True)
class DemoSeedResult:
    email: str
    refused: bool
    created_user: bool
    created_portfolio: bool
    transactions_inserted: int
    portfolio_id: str | None


def seed_demo_portfolio(session: Session, *, password: str) -> DemoSeedResult:
    """Create the demo book. ``password`` is hashed and never logged."""
    if len(password) < 8:
        raise ValueError("DEMO_USER_PASSWORD must be at least 8 characters")
    email = DEMO_EMAIL
    user = session.scalar(select(User).where(User.email == email))
    created_user = user is None
    if user is None:
        user = User(email=email, password_hash=hash_password(password))
        session.add(user)
        session.flush()

    portfolios = list(
        session.scalars(select(Portfolio).where(Portfolio.user_id == user.id))
    )
    labelled = next(
        (
            row
            for row in portfolios
            if (row.description or "").startswith(DEMO_BOOK_MARK)
        ),
        None,
    )
    if labelled is None and portfolios:
        return DemoSeedResult(
            email=email,
            refused=True,
            created_user=False,
            created_portfolio=False,
            transactions_inserted=0,
            portfolio_id=None,
        )

    created_portfolio = labelled is None
    portfolio = labelled or Portfolio(
        user_id=user.id,
        name=DEMO_PORTFOLIO_NAME,
        description=DEMO_PORTFOLIO_DESCRIPTION,
    )
    if created_portfolio:
        session.add(portfolio)
        session.flush()

    inserted = 0
    for fill in _FILLS:
        security = _listing(session, fill)
        already = session.scalar(
            select(Transaction.id).where(
                Transaction.portfolio_id == portfolio.id,
                Transaction.security_id == security.id,
                Transaction.transaction_type == "BUY",
                Transaction.timestamp == fill.timestamp,
            )
        )
        close = _stored_close(session, security.id, fill.timestamp)
        if already is not None:
            # A later history fill can replace the sample cost with that day's close.
            if close is not None:
                stored = session.get(Transaction, already)
                if stored is not None and stored.price == fill.price:
                    stored.price = close
            continue
        session.add(
            Transaction(
                portfolio_id=portfolio.id,
                security_id=security.id,
                transaction_type="BUY",
                quantity=fill.quantity,
                price=close if close is not None else fill.price,
                timestamp=fill.timestamp,
            )
        )
        inserted += 1
    session.flush()
    return DemoSeedResult(
        email=email,
        refused=False,
        created_user=created_user,
        created_portfolio=created_portfolio,
        transactions_inserted=inserted,
        portfolio_id=str(portfolio.id),
    )


def _stored_close(session: Session, security_id, when: datetime):
    """The stored adjusted close on or before the fill. None when no bar exists."""
    return session.scalar(
        select(Price.adjusted_close)
        .where(Price.security_id == security_id, Price.timestamp <= when)
        .order_by(Price.timestamp.desc())
        .limit(1)
    )


def _listing(session: Session, fill: _Fill) -> Security:
    existing = SecurityRepository(session).get_by_ticker(fill.ticker)
    if existing is not None:
        if not (existing.sector or "").strip():
            existing.sector = fill.sector
        return existing
    row = Security(
        ticker=fill.ticker,
        name=fill.name,
        exchange="NASDAQ",
        mic="XNAS",
        sector=fill.sector,
        country="US",
        currency="USD",
        asset_type="equity",
        provider="nasdaq",
        provider_symbol=fill.ticker,
        is_active=True,
    )
    session.add(row)
    session.flush()
    return row

