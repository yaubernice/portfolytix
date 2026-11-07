from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.services.analytics import (
    CloseBar,
    Fill,
    Split,
    allocation,
    build_value_series,
    daily_returns_of,
    external_cash_flows,
    max_drawdown,
    total_return,
)
from app.services.income import holding_term, projected_income, yield_on_cost
from app.services.lookthrough import Constituent, look_through
from app.services.lots import SplitEvent, TimedFill, fifo_lots

APPLE = uuid4()


def _buy(on: date, quantity: str, price: str) -> Fill:
    return Fill(
        on=on,
        security_id=APPLE,
        ticker="AAPL",
        is_buy=True,
        quantity=Decimal(quantity),
        price=Decimal(price),
    )


def test_deposit_is_not_a_return_and_does_not_double_count() -> None:
    fills = [_buy(date(2024, 1, 2), "10", "100")]
    bars = [
        CloseBar(APPLE, date(2024, 1, 2), Decimal("100")),
        CloseBar(APPLE, date(2024, 1, 3), Decimal("90")),
        CloseBar(APPLE, date(2024, 1, 4), Decimal("90")),
        CloseBar(APPLE, date(2024, 1, 5), Decimal("100")),
    ]
    flows = external_cash_flows(
        [
            (date(2024, 1, 4), "deposit", Decimal("500")),
            (date(2024, 1, 4), "dividend", Decimal("40")),
        ]
    )
    assert flows == [(date(2024, 1, 4), Decimal("500"))]
    points = build_value_series(fills, bars, flows)
    assert [point.value for point in points] == [
        Decimal("1000"),
        Decimal("900"),
        Decimal("1400"),
        Decimal("1500"),
    ]
    returns = daily_returns_of(points)
    assert returns[0] == Decimal("-0.1")
    assert returns[1] == Decimal("0")
    assert returns[2] == Decimal("100") / Decimal("1400")
    # Cash was added at the trough, so the last day's gain is diluted.
    diluted = (Decimal("-50") / Decimal("1400")).quantize(Decimal("0.00000001"))
    assert total_return(returns).quantize(Decimal("0.00000001")) == diluted
    assert max_drawdown(returns) == Decimal("-0.1")


def test_cash_funds_a_later_buy() -> None:
    fills = [_buy(date(2024, 1, 3), "10", "100")]
    bars = [
        CloseBar(APPLE, date(2024, 1, 2), Decimal("100")),
        CloseBar(APPLE, date(2024, 1, 3), Decimal("100")),
    ]
    points = build_value_series(
        fills,
        bars,
        [(date(2024, 1, 2), Decimal("1000"))],
    )
    assert points[-1].value == Decimal("1000")
    assert daily_returns_of(points) == [Decimal("0")]


def test_split_does_not_change_value() -> None:
    fills = [_buy(date(2024, 1, 2), "10", "20")]
    bars = [
        CloseBar(APPLE, date(2024, 1, 2), Decimal("20")),
        CloseBar(APPLE, date(2024, 1, 3), Decimal("10")),
        CloseBar(APPLE, date(2024, 1, 4), Decimal("11")),
    ]
    points = build_value_series(
        fills,
        bars,
        splits=[
            Split(
                on=date(2024, 1, 3),
                security_id=APPLE,
                numerator=Decimal("2"),
                denominator=Decimal("1"),
            )
        ],
    )
    assert [point.value for point in points] == [
        Decimal("200"),
        Decimal("200"),
        Decimal("220"),
    ]
    assert daily_returns_of(points) == [Decimal("0"), Decimal("0.1")]
    opened, closed = fifo_lots(
        [
            TimedFill(
                security_id=APPLE,
                ticker="AAPL",
                transaction_type="BUY",
                quantity=Decimal("10"),
                price=Decimal("20"),
                timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            )
        ],
        [
            SplitEvent(
                security_id=APPLE,
                ratio=Decimal("2"),
                timestamp=datetime(2024, 1, 3, tzinfo=UTC),
            )
        ],
    )
    assert closed == []
    assert opened[0].quantity == Decimal("20")
    assert opened[0].cost_price == Decimal("10")


def test_weights_sum_to_one() -> None:
    other = uuid4()
    lines = allocation(
        {APPLE: Decimal("2"), other: Decimal("1")},
        {APPLE: "AAPL", other: "MSFT"},
        {APPLE: Decimal("50"), other: Decimal("25")},
    )
    assert sum((line.weight for line in lines), Decimal("0")) == Decimal("1")


def test_income_uses_only_stored_inputs() -> None:
    assert yield_on_cost(Decimal("20"), Decimal("1000")) == Decimal("0.02")
    assert yield_on_cost(None, Decimal("1000")) is None
    assert projected_income([(Decimal("1000"), Decimal("0.03"))]) == Decimal("30")
    assert projected_income([(Decimal("1000"), None)]) is None
    assert holding_term(365) == "short"
    assert holding_term(366) == "long"


def test_look_through_leaves_a_fund_alone_without_constituents() -> None:
    rows, notes = look_through([("VOO", Decimal("1"))], {})
    assert rows[0].ticker == "VOO"
    assert rows[0].look_through_weight == Decimal("1")
    assert "No fund constituents" in notes[0]
    rows, notes = look_through(
        [("VOO", Decimal("1"))],
        {
            "VOO": [
                Constituent("AAPL", Decimal("0.07")),
                Constituent("MSFT", Decimal("0.06")),
            ]
        },
    )
    weights = {row.ticker: row.look_through_weight for row in rows}
    assert weights["AAPL"] == Decimal("0.07")
    assert weights["MSFT"] == Decimal("0.06")
    assert weights["VOO"] == Decimal("0.87")
    assert notes
