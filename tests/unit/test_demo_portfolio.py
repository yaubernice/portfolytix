from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.demo_portfolio import DEMO_EMAIL, seed_demo_portfolio
from app.db.models import Portfolio, Price, Transaction, User


def test_demo_book_is_repeatable_and_writes_no_prices(
    sqlite_session: Session,
) -> None:
    first = seed_demo_portfolio(sqlite_session, password="demo-password")
    assert first.refused is False
    assert first.created_user is True
    assert first.transactions_inserted == 8
    assert sqlite_session.scalar(select(func.count()).select_from(Price)) == 0

    second = seed_demo_portfolio(sqlite_session, password="demo-password")
    assert second.refused is False
    assert second.created_user is False
    assert second.transactions_inserted == 0
    assert sqlite_session.scalar(select(func.count()).select_from(Transaction)) == 8
    user = sqlite_session.scalar(select(User).where(User.email == DEMO_EMAIL))
    assert user is not None
    assert verify_password("demo-password", user.password_hash)


def test_demo_book_does_not_trade_in_another_portfolio(
    sqlite_session: Session,
) -> None:
    owner = User(email=DEMO_EMAIL, password_hash="not-a-real-hash")
    sqlite_session.add(owner)
    sqlite_session.flush()
    sqlite_session.add(
        Portfolio(user_id=owner.id, name="Personal", description="mine")
    )
    sqlite_session.flush()

    result = seed_demo_portfolio(sqlite_session, password="demo-password")
    assert result.refused is True
    assert result.transactions_inserted == 0
    assert sqlite_session.scalar(select(func.count()).select_from(Transaction)) == 0
    stored = sqlite_session.scalar(select(User).where(User.email == DEMO_EMAIL))
    assert stored is not None
    assert stored.password_hash == "not-a-real-hash"


def test_sample_fill_price_is_cost_basis_not_a_quote(
    sqlite_session: Session,
) -> None:
    seed_demo_portfolio(sqlite_session, password="demo-password")
    fills = list(sqlite_session.scalars(select(Transaction)))
    prices = {row.price for row in fills}
    assert prices == {
        Decimal("180"),
        Decimal("380"),
        Decimal("155"),
        Decimal("190"),
        Decimal("110"),
        Decimal("330"),
        Decimal("170"),
        Decimal("70"),
    }
    assert len(fills) == 8
    assert sqlite_session.scalar(select(func.count()).select_from(Price)) == 0
