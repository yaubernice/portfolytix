from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.services.lots import SplitEvent, TimedFill, average_cost_with_splits, fifo_lots


def _buy(security_id, ticker, quantity, price, day) -> TimedFill:
    return TimedFill(
        security_id=security_id,
        ticker=ticker,
        transaction_type="BUY",
        quantity=Decimal(quantity),
        price=Decimal(price),
        timestamp=datetime(2026, 1, day, tzinfo=UTC),
    )


def test_fifo_realizes_the_oldest_lot_first() -> None:
    security_id = uuid4()
    opened, closed = fifo_lots(
        [
            _buy(security_id, "AAA", "10", "10", 2),
            _buy(security_id, "AAA", "5", "20", 3),
            TimedFill(
                security_id=security_id,
                ticker="AAA",
                transaction_type="SELL",
                quantity=Decimal("12"),
                price=Decimal("15"),
                timestamp=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        ]
    )
    assert len(closed) == 2
    assert closed[0].quantity == Decimal("10")
    assert closed[0].realized_pl == Decimal("50")
    assert closed[1].quantity == Decimal("2")
    assert opened[0].quantity == Decimal("3")
    assert opened[0].cost_price == Decimal("20")


def test_split_scales_open_lots_and_average_cost() -> None:
    security_id = uuid4()
    fills = [_buy(security_id, "AAA", "10", "20", 2)]
    splits = [
        SplitEvent(
            security_id=security_id,
            ratio=Decimal("2"),
            timestamp=datetime(2026, 3, 1, tzinfo=UTC),
        )
    ]
    opened, closed = fifo_lots(fills, splits)
    assert closed == []
    assert opened[0].quantity == Decimal("20")
    assert opened[0].cost_price == Decimal("10")
    costs = average_cost_with_splits(fills, splits)
    assert costs[0].quantity == Decimal("20")
    assert costs[0].avg_cost == Decimal("10")
