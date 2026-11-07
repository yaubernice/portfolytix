from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import CashMovement, Fundamental, Price, Security, ShareSplit
from app.quotes.models import LiveQuote
from app.quotes.provider_marks import provider_quotes
from app.quotes.store import QuoteStore
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.security_repository import SecurityRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.position import (
    LotOut,
    PositionContribution,
    PositionOut,
    PositionsResponse,
    PriceFreshness,
    WeightBucket,
)
from app.services.income import (
    fund_expense,
    holding_term,
    projected_income,
    yield_on_cost,
)
from app.services.ledger_service import usd_amount
from app.services.lots import (
    SplitEvent,
    TimedFill,
    average_cost_with_splits,
    fifo_lots,
)
from app.services.positions import AverageCost, CostFill, average_cost_positions


class PositionService:
    """Holdings plus average cost, marked with the live quote or last close."""

    def __init__(
        self,
        session: Session,
        user_id: UUID,
        quotes: QuoteStore,
    ) -> None:
        self.user_id = user_id
        self.session = session
        self.portfolios = PortfolioRepository(session)
        self.transactions = TransactionRepository(session)
        self.securities = SecurityRepository(session)
        self.quotes = quotes

    def list_positions(self, portfolio_id: UUID) -> PositionsResponse:
        if self.portfolios.get_owned(portfolio_id, self.user_id) is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        stored = self.transactions.list_for_portfolio(portfolio_id)
        fills = [
            CostFill(
                security_id=row.security_id,
                ticker=row.security.ticker,
                transaction_type=row.transaction_type,
                quantity=row.quantity,
                price=row.price,
            )
            for row in stored
        ]
        timed = [
            TimedFill(
                security_id=row.security_id,
                ticker=row.security.ticker,
                transaction_type=row.transaction_type,
                quantity=row.quantity,
                price=row.price,
                timestamp=row.timestamp,
            )
            for row in stored
        ]
        split_events = self._splits(portfolio_id)
        costs = (
            average_cost_with_splits(timed, split_events)
            if split_events
            else average_cost_positions(fills)
        )
        listings = {
            row.id: row
            for row in self.session.scalars(
                select(Security).where(
                    Security.id.in_([item.security_id for item in costs])
                )
            )
        } if costs else {}
        live = {quote.ticker: quote for quote in self.quotes.snapshot()}
        if settings.provider_marks:
            fetched = provider_quotes(
                [row.ticker for row in costs],
                self.quotes,
            )
            live = {**live, **fetched}
        positions = [
            self._position(row, live.get(row.ticker), listings.get(row.security_id))
            for row in costs
        ]
        positions = [self._in_dollars(row) for row in positions]
        priced = [
            row.reporting_value
            for row in positions
            if row.reporting_value is not None
        ]
        total = sum(priced, Decimal("0"))
        if total > 0:
            weighted: list[PositionOut] = []
            for row in positions:
                weight = (
                    row.reporting_value / total
                    if row.reporting_value is not None
                    else None
                )
                weighted.append(row.model_copy(update={"weight": weight}))
            positions = weighted
        day_values = [row.day_pl for row in positions if row.day_pl is not None]
        day_pl = sum(day_values, Decimal("0")) if day_values else None
        cost_values = [
            row.cost_basis for row in positions if row.cost_basis is not None
        ]
        cost_basis = sum(cost_values, Decimal("0")) if cost_values else None
        unrealized_values = [
            row.unrealized_pl for row in positions if row.unrealized_pl is not None
        ]
        unrealized_pl = (
            sum(unrealized_values, Decimal("0")) if unrealized_values else None
        )
        contributors = sorted(
            (row for row in positions if row.day_pl is not None and row.day_pl > 0),
            key=lambda row: row.day_pl or Decimal("0"),
            reverse=True,
        )
        detractors = sorted(
            (row for row in positions if row.day_pl is not None and row.day_pl < 0),
            key=lambda row: row.day_pl or Decimal("0"),
        )
        # A holding with no stored or provider price is unknown, not worth zero.
        cash, income = self._cash_totals(portfolio_id)
        market_value = total if priced else None
        if cash is not None:
            market_value = (market_value or Decimal("0")) + cash
        opened, closed = fifo_lots(timed, split_events)
        realized_pl = (
            sum((lot.realized_pl for lot in closed), Decimal("0")) if closed else None
        )
        yields, expenses = self._stored_rates(
            [row.security_id for row in positions]
        )
        projected = projected_income(
            [
                (row.reporting_value, yields.get(row.security_id))
                for row in positions
                if row.reporting_value is not None
            ]
        )
        expense = fund_expense(
            [
                (row.reporting_value, expenses.get(row.security_id))
                for row in positions
                if row.reporting_value is not None
            ]
        )
        warnings = _warnings(positions)
        return PositionsResponse(
            portfolio_id=portfolio_id,
            cost_basis=cost_basis,
            market_value=market_value,
            unrealized_pl=unrealized_pl,
            day_pl=day_pl,
            cash=cash,
            income=income,
            realized_pl=realized_pl,
            yield_on_cost=yield_on_cost(income, cost_basis),
            projected_income=projected,
            fund_expense=expense,
            top_contributors=[_contribution(row) for row in contributors[:3]],
            top_detractors=[_contribution(row) for row in detractors[:3]],
            sector_allocation=_buckets(
                [(row.sector, row.reporting_value) for row in positions],
                ("Cash", cash) if cash not in (None, Decimal("0")) else None,
            ),
            asset_allocation=_buckets(
                [(row.asset_type, row.reporting_value) for row in positions],
                ("Cash", cash) if cash not in (None, Decimal("0")) else None,
            ),
            currency_allocation=_buckets(
                [(row.currency, row.reporting_value) for row in positions],
                ("USD", cash) if cash not in (None, Decimal("0")) else None,
            ),
            lots=_lot_rows(opened, closed),
            warnings=warnings,
            positions=positions,
        )

    def _stored_rates(
        self,
        security_ids: list[UUID],
    ) -> tuple[dict[UUID, Decimal | None], dict[UUID, Decimal | None]]:
        if not security_ids:
            return {}, {}
        rows = self.session.scalars(
            select(Fundamental).where(Fundamental.security_id.in_(security_ids))
        )
        yields: dict[UUID, Decimal | None] = {}
        expenses: dict[UUID, Decimal | None] = {}
        for row in rows:
            yields[row.security_id] = row.dividend_yield
            expenses[row.security_id] = row.expense_ratio
        return yields, expenses

    def _position(
        self,
        row: AverageCost,
        quote: LiveQuote | None,
        security: Security | None,
    ) -> PositionOut:
        previous = quote.previous_close if quote is not None else None
        price = quote.price if quote is not None else None
        source = quote.source if quote is not None else "database"
        timeliness = quote.timeliness if quote is not None else "unavailable"
        bar_at = None
        if price is None:
            closes = self._recent_bars(row.security_id)
            if closes:
                price, bar_at = closes[-1]
                source = "database"
                timeliness = "historical"
                if previous is None and len(closes) > 1:
                    previous = closes[-2][0]
        market_value = price * row.quantity if price is not None else None
        cost_basis = (
            row.avg_cost * row.quantity if row.avg_cost is not None else None
        )
        unrealized = (
            (price - row.avg_cost) * row.quantity
            if price is not None and row.avg_cost is not None
            else None
        )
        day_pl = (
            (price - previous) * row.quantity
            if price is not None and previous is not None
            else None
        )
        return PositionOut(
            security_id=row.security_id,
            ticker=row.ticker,
            quantity=row.quantity,
            average_cost=row.avg_cost,
            avg_cost=row.avg_cost,
            cost_basis=cost_basis,
            current_price=price,
            price=price,
            previous_close=previous,
            market_value=market_value,
            unrealized_pl=unrealized,
            day_pl=day_pl,
            sector=security.sector if security is not None else "",
            asset_type=security.asset_type if security is not None else "equity",
            currency=(security.currency if security is not None else "USD") or "USD",
            price_source=source,
            price_timeliness=timeliness,
            quote_provider_timestamp=(
                quote.provider_timestamp if quote is not None else None
            ),
            quote_received_at=quote.received_at if quote is not None else None,
            quote_age_seconds=quote.age_seconds if quote is not None else None,
            freshness=PriceFreshness(
                source=source,
                timeliness=timeliness,
                as_of=(
                    quote.provider_timestamp if quote is not None else bar_at
                ),
                received_at=quote.received_at if quote is not None else None,
                age_seconds=quote.age_seconds if quote is not None else None,
            ),
        )

    def _recent_bars(self, security_id: UUID) -> list[tuple[Decimal, datetime]]:
        statement = (
            select(Price.adjusted_close, Price.timestamp)
            .where(Price.security_id == security_id)
            .order_by(Price.timestamp.desc())
            .limit(2)
        )
        rows = list(self.session.execute(statement))
        rows.reverse()
        return [(row[0], row[1]) for row in rows]

    def _splits(self, portfolio_id: UUID) -> list[SplitEvent]:
        rows = self.session.scalars(
            select(ShareSplit).where(ShareSplit.portfolio_id == portfolio_id)
        )
        return [
            SplitEvent(
                security_id=row.security_id,
                ratio=Decimal(row.numerator) / Decimal(row.denominator),
                timestamp=row.timestamp,
            )
            for row in rows
        ]

    def _cash_totals(self, portfolio_id: UUID) -> tuple[Decimal | None, Decimal | None]:
        rows = list(
            self.session.scalars(
                select(CashMovement).where(CashMovement.portfolio_id == portfolio_id)
            )
        )
        if not rows:
            return None, None
        cash = Decimal("0")
        income = Decimal("0")
        dividends = False
        for row in rows:
            signed = usd_amount(row.amount, row.currency, row.fx_rate)
            if signed is None:
                continue
            if row.kind == "withdrawal":
                cash -= signed
            else:
                cash += signed
            if row.kind == "dividend":
                dividends = True
                income += signed
        return cash, income if dividends else None

    def _in_dollars(self, row: PositionOut) -> PositionOut:
        rate = self._fx_rate(row.currency)
        if rate is None or row.market_value is None:
            return row.model_copy(update={"reporting_value": None, "fx_rate": None})
        return row.model_copy(
            update={
                "fx_rate": rate,
                "reporting_value": row.market_value * rate,
                "market_value": row.market_value * rate,
                "cost_basis": None if row.cost_basis is None else row.cost_basis * rate,
                "unrealized_pl": (
                    None if row.unrealized_pl is None else row.unrealized_pl * rate
                ),
                "day_pl": None if row.day_pl is None else row.day_pl * rate,
                "current_price": (
                    None if row.current_price is None else row.current_price * rate
                ),
                "price": None if row.price is None else row.price * rate,
            }
        )

    def _fx_rate(self, currency: str) -> Decimal | None:
        code = (currency or "USD").upper()
        if code == "USD":
            return Decimal("1")
        try:
            listing = self.securities.get_by_ticker(f"{code}USD=X")
        except ConflictError:
            return None
        if listing is None:
            return None
        closes = self._recent_bars(listing.id)
        if not closes:
            return None
        return closes[-1][0]


def _warnings(positions: list[PositionOut]) -> list[str]:
    notes: list[str] = []
    sector_value: dict[str, Decimal] = {}
    for row in positions:
        if row.weight is not None and row.weight >= Decimal("0.25"):
            notes.append(
                f"{row.ticker} is {_pct(row.weight)} of priced holdings."
            )
        if row.reporting_value is None and row.market_value is not None:
            notes.append(
                f"No stored USD rate for {row.currency}. "
                f"{row.ticker} is left out of the dollar total."
            )
        if row.reporting_value is not None and row.sector:
            sector_value[row.sector] = (
                sector_value.get(row.sector, Decimal("0")) + row.reporting_value
            )
    sector_total = sum(sector_value.values(), Decimal("0"))
    if sector_total > 0:
        for sector, value in sector_value.items():
            weight = value / sector_total
            if weight >= Decimal("0.40"):
                notes.append(f"{sector} is {_pct(weight)} of priced holdings.")
    return notes


def _buckets(
    pairs: list[tuple[str, Decimal | None]],
    extra: tuple[str, Decimal] | None,
) -> list[WeightBucket]:
    totals: dict[str, Decimal] = {}
    for label, value in pairs:
        if value is None:
            continue
        key = label or "Unclassified"
        totals[key] = totals.get(key, Decimal("0")) + value
    if extra is not None and extra[1] != 0:
        totals[extra[0]] = totals.get(extra[0], Decimal("0")) + extra[1]
    grand = sum(totals.values(), Decimal("0"))
    if grand <= 0:
        return []
    rows = [
        WeightBucket(label=label, market_value=value, weight=value / grand)
        for label, value in totals.items()
    ]
    rows.sort(key=lambda row: row.weight, reverse=True)
    return rows


def _held(opened_at: datetime, closed_at: datetime | None = None) -> tuple[int, str]:
    end = closed_at or datetime.now(UTC)
    start = opened_at if opened_at.tzinfo else opened_at.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    days = max(0, (end.date() - start.date()).days)
    return days, holding_term(days)


def _lot_rows(opened, closed) -> list[LotOut]:
    rows = []
    for lot in opened:
        days, term = _held(lot.opened_at)
        rows.append(
            LotOut(
                ticker=lot.ticker,
                quantity=lot.quantity,
                cost_price=lot.cost_price,
                opened_at=lot.opened_at,
                status="open",
                held_days=days,
                holding_period=term,  # type: ignore[arg-type]
            )
        )
    for lot in closed:
        days, term = _held(lot.opened_at, lot.closed_at)
        rows.append(
            LotOut(
                ticker=lot.ticker,
                quantity=lot.quantity,
                cost_price=lot.cost_price,
                opened_at=lot.opened_at,
                status="closed",
                sell_price=lot.sell_price,
                realized_pl=lot.realized_pl,
                closed_at=lot.closed_at,
                held_days=days,
                holding_period=term,  # type: ignore[arg-type]
            )
        )
    return rows


def _pct(value: Decimal) -> str:
    points = (value * Decimal("100")).quantize(Decimal("0.1"))
    return f"{points}%"


def _contribution(row: PositionOut) -> PositionContribution:
    assert row.day_pl is not None
    return PositionContribution(
        ticker=row.ticker,
        day_pl=row.day_pl,
        market_value=row.market_value,
        weight=row.weight,
    )
