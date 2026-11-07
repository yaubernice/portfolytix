"""First-in, first-out lots and split-adjusted average cost.

Unrealized P/L on a position stays average cost. Lots are a separate record
of which shares are still open and what a sale realized.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.db.models.transaction import TransactionType
from app.services.positions import AverageCost, CostFill, average_cost_positions


@dataclass(frozen=True, slots=True)
class TimedFill:
    security_id: UUID
    ticker: str
    transaction_type: str
    quantity: Decimal
    price: Decimal
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class SplitEvent:
    security_id: UUID
    ratio: Decimal
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class OpenLot:
    security_id: UUID
    ticker: str
    quantity: Decimal
    cost_price: Decimal
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class ClosedLot:
    security_id: UUID
    ticker: str
    quantity: Decimal
    cost_price: Decimal
    sell_price: Decimal
    realized_pl: Decimal
    opened_at: datetime
    closed_at: datetime


def fifo_lots(
    fills: list[TimedFill],
    splits: list[SplitEvent] | None = None,
) -> tuple[list[OpenLot], list[ClosedLot]]:
    """Replay fills and splits in time. A split scales lots opened before it."""
    open_lots: dict[UUID, list[OpenLot]] = {}
    closed: list[ClosedLot] = []
    events: list[tuple[datetime, int, int, str, object]] = []
    for index, fill in enumerate(fills):
        events.append((fill.timestamp, 0, index, "fill", fill))
    for index, split in enumerate(splits or []):
        events.append((split.timestamp, 1, index, "split", split))
    events.sort(key=lambda row: (row[0], row[1], row[2]))

    for _timestamp, _kind_order, _index, kind, event in events:
        if kind == "split":
            assert isinstance(event, SplitEvent)
            lots = open_lots.get(event.security_id, [])
            open_lots[event.security_id] = [
                OpenLot(
                    security_id=lot.security_id,
                    ticker=lot.ticker,
                    quantity=lot.quantity * event.ratio,
                    cost_price=lot.cost_price / event.ratio,
                    opened_at=lot.opened_at,
                )
                for lot in lots
            ]
            continue
        assert isinstance(event, TimedFill)
        book = open_lots.setdefault(event.security_id, [])
        if event.transaction_type == TransactionType.SELL.value:
            remaining = event.quantity
            while remaining > 0 and book:
                lot = book[0]
                taken = lot.quantity if lot.quantity <= remaining else remaining
                closed.append(
                    ClosedLot(
                        security_id=event.security_id,
                        ticker=event.ticker,
                        quantity=taken,
                        cost_price=lot.cost_price,
                        sell_price=event.price,
                        realized_pl=(event.price - lot.cost_price) * taken,
                        opened_at=lot.opened_at,
                        closed_at=event.timestamp,
                    )
                )
                leftover = lot.quantity - taken
                if leftover == 0:
                    book.pop(0)
                else:
                    book[0] = OpenLot(
                        security_id=lot.security_id,
                        ticker=lot.ticker,
                        quantity=leftover,
                        cost_price=lot.cost_price,
                        opened_at=lot.opened_at,
                    )
                remaining -= taken
            continue
        book.append(
            OpenLot(
                security_id=event.security_id,
                ticker=event.ticker,
                quantity=event.quantity,
                cost_price=event.price,
                opened_at=event.timestamp,
            )
        )
    opened = [lot for lots in open_lots.values() for lot in lots if lot.quantity > 0]
    opened.sort(key=lambda lot: (lot.ticker, lot.opened_at))
    return opened, closed


def average_cost_with_splits(
    fills: list[TimedFill],
    splits: list[SplitEvent],
) -> list[AverageCost]:
    """Average cost, with splits scaling shares held at the split time.

    Cost in currency does not change. The average per share does.
    """
    if not splits:
        return average_cost_positions(
            [
                CostFill(
                    security_id=fill.security_id,
                    ticker=fill.ticker,
                    transaction_type=fill.transaction_type,
                    quantity=fill.quantity,
                    price=fill.price,
                )
                for fill in fills
            ]
        )
    quantity: dict[UUID, Decimal] = {}
    cost: dict[UUID, Decimal] = {}
    tickers: dict[UUID, str] = {}
    events: list[tuple[datetime, int, int, str, object]] = []
    for index, fill in enumerate(fills):
        events.append((fill.timestamp, 0, index, "fill", fill))
    for index, split in enumerate(splits):
        events.append((split.timestamp, 1, index, "split", split))
    events.sort(key=lambda row: (row[0], row[1], row[2]))
    for _timestamp, _kind_order, _index, kind, event in events:
        if kind == "split":
            assert isinstance(event, SplitEvent)
            held = quantity.get(event.security_id, Decimal("0"))
            if held > 0:
                quantity[event.security_id] = held * event.ratio
            continue
        assert isinstance(event, TimedFill)
        tickers[event.security_id] = event.ticker
        held = quantity.get(event.security_id, Decimal("0"))
        booked = cost.get(event.security_id, Decimal("0"))
        if event.transaction_type == TransactionType.SELL.value:
            if held > 0:
                booked -= (booked / held) * event.quantity
            held -= event.quantity
        else:
            booked += event.quantity * event.price
            held += event.quantity
        if held == 0:
            booked = Decimal("0")
        quantity[event.security_id] = held
        cost[event.security_id] = booked
    rows: list[AverageCost] = []
    for security_id, held in quantity.items():
        if held == 0:
            continue
        booked = cost[security_id]
        rows.append(
            AverageCost(
                security_id=security_id,
                ticker=tickers[security_id],
                quantity=held,
                avg_cost=booked / held if held > 0 else None,
            )
        )
    rows.sort(key=lambda row: row.ticker)
    return rows
