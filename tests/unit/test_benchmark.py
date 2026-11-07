from datetime import date
from decimal import Decimal

from app.services.benchmark import indexed_returns, pearson


def test_benchmark_is_indexed_to_the_first_shared_close() -> None:
    days = [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)]
    closes = {
        date(2026, 1, 2): Decimal("100"),
        date(2026, 1, 6): Decimal("110"),
    }
    indexed = indexed_returns(days, closes)
    assert indexed == [
        (date(2026, 1, 2), Decimal("0")),
        (date(2026, 1, 6), Decimal("0.1")),
    ]


def test_benchmark_without_two_closes_is_empty() -> None:
    assert indexed_returns([date(2026, 1, 2)], {date(2026, 1, 2): Decimal("100")}) == []


def test_pearson_needs_five_pairs() -> None:
    short = [(Decimal("1"), Decimal("1"))] * 4
    assert pearson(short) is None
    pairs = [
        (Decimal("1"), Decimal("2")),
        (Decimal("2"), Decimal("4")),
        (Decimal("3"), Decimal("6")),
        (Decimal("4"), Decimal("8")),
        (Decimal("5"), Decimal("10")),
    ]
    assert pearson(pairs) == Decimal("1.0000")


def test_beta_is_one_when_the_portfolio_moves_with_the_benchmark() -> None:
    from app.services.benchmark import beta

    pairs = [
        (Decimal("0.01"), Decimal("0.01")),
        (Decimal("0.02"), Decimal("0.02")),
        (Decimal("-0.01"), Decimal("-0.01")),
        (Decimal("0.00"), Decimal("0.00")),
        (Decimal("0.03"), Decimal("0.03")),
    ]
    assert beta(pairs) == Decimal("1.0000")
    assert beta(pairs[:4]) is None
