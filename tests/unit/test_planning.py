from decimal import Decimal

from app.services.planning import (
    buy_after_runup,
    contributed,
    equal_weight_amounts,
    future_value,
    required_monthly,
    shares_at_price,
)


def test_zero_rate_is_the_sum_of_the_contributions() -> None:
    value = future_value(Decimal("1000"), Decimal("100"), 12, Decimal("0"))
    assert value == Decimal("2200")
    assert contributed(Decimal("200"), 6) == Decimal("1200")
    assert shares_at_price(Decimal("1200"), Decimal("100")) == Decimal("12")
    assert shares_at_price(Decimal("1200"), None) is None


def test_required_contribution_at_zero_closes_the_gap() -> None:
    payment = required_monthly(Decimal("1000"), Decimal("2200"), 12, Decimal("0"))
    assert payment == Decimal("100")


def test_equal_weight_uses_only_the_current_names() -> None:
    split = equal_weight_amounts(
        [("AAPL", Decimal("0.8")), ("JPM", Decimal("0.2"))],
        Decimal("100"),
    )
    assert split == [("JPM", Decimal("100"))]


def test_runup_needs_a_stored_close() -> None:
    assert buy_after_runup(Decimal("110"), Decimal("100")) is True
    assert buy_after_runup(Decimal("105"), Decimal("100")) is False
    assert buy_after_runup(Decimal("110"), None) is None
