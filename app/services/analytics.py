"""Portfolio return math. Pure functions — no database, no HTTP.

Assumptions (also returned on the API and in the README):

Time-weighted return (TWR)
    Daily return strips external cash so a deposit is not a gain:
    r_t = (V_t - V_{t-1} - CF_t) / V_{t-1}
    A buy is external only for the part not paid from stored cash.
    A sale stays in cash until it is withdrawn. Deposits and withdrawals
    are external. Dividend cash is not added: closes are adjusted.

    total_return is the geometric product of those daily returns, not
    annualized: Π(1 + r_t) − 1.

Price
    Holdings are marked at ``adjusted_close`` on or before that day.
    If no close exists yet, the last fill price is used.

Volatility
    Sample standard deviation (n−1) of daily TWR, then annualized:
    σ_daily × √252. Needs at least two daily returns.

Sharpe ratio
    (mean(r_daily) − rf/252) / σ_daily.
    rf is an annual decimal (default 0.05). Arithmetic daily rf.
    Undefined when σ is 0.

Max drawdown
    On the TWR wealth index that starts at 1:
    DD_t = W_t / running_max(W) − 1. Reported value is min(DD_t) ≤ 0.

Allocation
    Current quantity × latest mark / portfolio market value.

These figures are a teaching implementation, not investment advice.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.db.models.transaction import TransactionType

ZERO = Decimal("0")
ONE = Decimal("1")
DEFAULT_TRADING_DAYS = 252
DEFAULT_RISK_FREE_RATE = Decimal("0.05")


@dataclass(frozen=True, slots=True) #holding data
class Fill: #does not want to depend on SQLAlchemy/database objects
    on: date
    security_id: UUID
    ticker: str
    is_buy: bool
    quantity: Decimal
    price: Decimal

    @property
    def cash_flow(self) -> Decimal:
        notional = self.quantity * self.price
        return notional if self.is_buy else -notional #is sell then it is negative CF

    @property
    def signed_quantity(self) -> Decimal:
        return self.quantity if self.is_buy else -self.quantity


# frozen=True: once a Fill/CloseBar is created, its fields cannot be modified
@dataclass(frozen=True, slots=True)
class CloseBar: #closing price of the security on a given day
    security_id: UUID
    on: date
    close: Decimal


@dataclass(frozen=True, slots=True)
class Split:
    """Shares already held are multiplied by numerator / denominator."""

    on: date
    security_id: UUID
    numerator: Decimal
    denominator: Decimal


@dataclass(frozen=True, slots=True)
class ValuePoint: #value of the portfolio on a given day
    on: date
    value: Decimal
    cash_flow: Decimal
    daily_pl: Decimal | None
    daily_return: Decimal | None
    cumulative_return: Decimal | None
    drawdown: Decimal


@dataclass(frozen=True, slots=True)
class AllocationLine: #allocation of the portfolio on a given day
    security_id: UUID
    ticker: str
    quantity: Decimal
    price: Decimal
    market_value: Decimal
    weight: Decimal


@dataclass(frozen=True, slots=True)
class _PriceSeries: #helper class to store the dates and prices of the security
    dates: list[date]
    prices: list[Decimal]


class PriceIndex: 
    """Last ``adjusted_close`` on or before a date, per security."""

    def __init__(self, bars: list[CloseBar]) -> None:
        grouped: dict[UUID, list[CloseBar]] = {}
        for bar in bars:
            grouped.setdefault(bar.security_id, []).append(bar)
        self._series: dict[UUID, _PriceSeries] = {}
        for security_id, rows in grouped.items():
            rows.sort(key=lambda bar: bar.on)
            self._series[security_id] = _PriceSeries(
                dates=[bar.on for bar in rows],
                prices=[bar.close for bar in rows],
            )

    def on_or_before(self, security_id: UUID, on: date) -> Decimal | None:
        # latest price on or before the requested date
        series = self._series.get(security_id)
        if series is None:
            return None
        # insertion point while preserving order; -1 is the last date <= on
        index = bisect_right(series.dates, on) - 1
        if index < 0:
            return None
        return series.prices[index]

    def latest(self, security_id: UUID) -> Decimal | None:
        # latest available price for a security
        series = self._series.get(security_id)
        if series is None or not series.prices:
            return None
        return series.prices[-1]

    def all_dates(self) -> set[date]:
        # every date represented by the price series 
        dates: set[date] = set()
        for series in self._series.values():
            dates.update(series.dates)
        return dates


def sample_stdev(values: list[Decimal]) -> Decimal | None:
    count = len(values)
    if count < 2:
        return None
    mean = sum(values, ZERO) / Decimal(count)
    squared = sum((item - mean) ** 2 for item in values)
    variance = squared / Decimal(count - 1)
    return variance.sqrt()


def total_return(daily_returns: list[Decimal]) -> Decimal:
    wealth = ONE
    for item in daily_returns:
        wealth *= ONE + item
    return wealth - ONE


def annualized_return(
    daily_returns: list[Decimal],
    trading_days_per_year: int = DEFAULT_TRADING_DAYS,
) -> Decimal | None:
    """Geometric annualization of TWR: (1 + TWR)^(252/n) − 1."""
    count = len(daily_returns)
    if count == 0:
        return None
    growth = ONE + total_return(daily_returns)
    if growth <= 0:
        return None
    exponent = Decimal(trading_days_per_year) / Decimal(count)
    return growth ** exponent - ONE


def annualized_volatility(
    daily_returns: list[Decimal],
    trading_days_per_year: int = DEFAULT_TRADING_DAYS,
) -> Decimal | None:
    sigma = sample_stdev(daily_returns)
    if sigma is None:
        return None
    return sigma * Decimal(trading_days_per_year).sqrt()


def sharpe_ratio(
    daily_returns: list[Decimal],
    risk_free_rate_annual: Decimal = DEFAULT_RISK_FREE_RATE,
    trading_days_per_year: int = DEFAULT_TRADING_DAYS,
) -> Decimal | None:
    sigma = sample_stdev(daily_returns)
    if sigma is None or sigma == ZERO:
        return None
    mean = sum(daily_returns, ZERO) / Decimal(len(daily_returns))
    rf_daily = risk_free_rate_annual / Decimal(trading_days_per_year)
    return (mean - rf_daily) / sigma


def max_drawdown(daily_returns: list[Decimal]) -> Decimal:
    wealth = ONE
    peak = ONE
    worst = ZERO
    for item in daily_returns:
        wealth *= ONE + item
        if wealth > peak:
            peak = wealth
        drawdown = wealth / peak - ONE
        if drawdown < worst:
            worst = drawdown
    return worst


def daily_profit_loss(
    previous_value: Decimal | None,
    value: Decimal,
    cash_flow: Decimal,
) -> Decimal | None:
    """Absolute daily portfolio P/L with external cash flows removed."""
    if previous_value is None:
        return None
    return value - previous_value - cash_flow


def point_in_time_drawdowns(
    daily_returns: list[Decimal | None],
) -> list[Decimal]:
    """Drawdown at each observation on the same TWR wealth index as max_drawdown."""
    wealth = ONE
    peak = ONE
    result: list[Decimal] = []
    for item in daily_returns:
        if item is not None:
            wealth *= ONE + item
            peak = max(peak, wealth)
        result.append(wealth / peak - ONE)
    return result


def allocation(
    quantities: dict[UUID, Decimal],
    tickers: dict[UUID, str],
    prices: dict[UUID, Decimal],
) -> list[AllocationLine]:
    lines: list[AllocationLine] = []
    total = ZERO
    for security_id, quantity in quantities.items():
        if quantity == ZERO:
            continue
        price = prices.get(security_id)
        if price is None:
            continue
        market_value = quantity * price
        lines.append(
            AllocationLine(
                security_id=security_id,
                ticker=tickers[security_id],
                quantity=quantity,
                price=price,
                market_value=market_value,
                weight=ZERO,
            )
        )
        total += market_value
    if total == ZERO:
        return []
    weighted = [
        AllocationLine(
            security_id=line.security_id,
            ticker=line.ticker,
            quantity=line.quantity,
            price=line.price,
            market_value=line.market_value,
            weight=line.market_value / total,
        )
        for line in lines
    ]
    weighted.sort(key=lambda line: line.ticker)
    return weighted


def external_cash_flows(
    rows: list[tuple[date, str, Decimal]],
) -> list[tuple[date, Decimal]]:
    """Deposits are positive and withdrawals negative.

    Dividend rows are omitted. Adjusted closes already include that
    adjustment, so adding the cash again would count it twice.
    """
    flows: list[tuple[date, Decimal]] = []
    for day, kind, usd in rows:
        if kind == "deposit":
            flows.append((day, usd))
        elif kind == "withdrawal":
            flows.append((day, -usd))
    return flows


def build_value_series(
    fills: list[Fill],
    bars: list[CloseBar],
    cash_flows: list[tuple[date, Decimal]] | None = None,
    splits: list[Split] | None = None,
) -> list[ValuePoint]:
    """Walk market days, mark holdings, and strip external cash from TWR.

    Stored cash pays for a buy before the rest of that buy is treated as
    new money. Sale proceeds stay in cash. ``cash_flows`` are deposits
    and withdrawals only.
    """
    if not fills and not cash_flows:
        return []

    index = PriceIndex(bars)
    fills_by_day: dict[date, list[Fill]] = {}
    fallback_price: dict[UUID, Decimal] = {}
    tickers: dict[UUID, str] = {}
    for fill in fills:
        fills_by_day.setdefault(fill.on, []).append(fill)
        fallback_price[fill.security_id] = fill.price
        tickers[fill.security_id] = fill.ticker
    external_by_day: dict[date, Decimal] = {}
    for day, amount in cash_flows or []:
        external_by_day[day] = external_by_day.get(day, ZERO) + amount
    splits_by_day: dict[date, list[Split]] = {}
    for split in splits or []:
        splits_by_day.setdefault(split.on, []).append(split)

    dated = set(fills_by_day) | set(external_by_day) | set(splits_by_day)
    first_day = min(dated) if dated else None
    if first_day is None:
        return []
    calendar = sorted(
        {day for day in index.all_dates() if day >= first_day} | dated
    )

    holdings: dict[UUID, Decimal] = {}
    cash_balance = ZERO
    pending_external = ZERO
    pending_trade = ZERO
    previous_value: Decimal | None = None
    wealth = ONE
    peak = ONE
    points: list[ValuePoint] = []

    for on in calendar:
        external = external_by_day.get(on, ZERO)
        incoming = external if external > ZERO else ZERO
        outgoing = external if external < ZERO else ZERO
        cash_balance += incoming
        trade_external = ZERO
        for split in splits_by_day.get(on, []):
            held = holdings.get(split.security_id)
            if held is None or split.denominator == ZERO:
                continue
            holdings[split.security_id] = (
                held * split.numerator / split.denominator
            )
        for fill in fills_by_day.get(on, []):
            notional = fill.quantity * fill.price
            fallback_price[fill.security_id] = fill.price
            tickers[fill.security_id] = fill.ticker
            if fill.is_buy:
                funded = min(max(cash_balance, ZERO), notional)
                cash_balance -= funded
                trade_external += notional - funded
            else:
                cash_balance += notional
            current = holdings.get(fill.security_id, ZERO) + fill.signed_quantity
            if current == ZERO:
                holdings.pop(fill.security_id, None)
            else:
                holdings[fill.security_id] = current
        cash_balance += outgoing

        if holdings:
            marked = _mark_to_market(holdings, on, index, fallback_price)
            if marked is None:
                pending_external += external
                pending_trade += trade_external
                continue
        else:
            marked = ZERO
        cash_flow = pending_external + pending_trade + external + trade_external
        pending_external = ZERO
        pending_trade = ZERO
        value = marked + cash_balance

        daily: Decimal | None = None
        daily_pl = daily_profit_loss(previous_value, value, cash_flow)
        cumulative: Decimal | None = None
        if previous_value is not None and previous_value != ZERO:
            assert daily_pl is not None
            daily = daily_pl / previous_value
            wealth *= ONE + daily
            peak = max(peak, wealth)
            cumulative = wealth - ONE
        elif value > ZERO:
            cumulative = ZERO

        if previous_value is None and value == ZERO:
            continue

        points.append(
            ValuePoint(
                on=on,
                value=value,
                cash_flow=cash_flow,
                daily_pl=daily_pl,
                daily_return=daily,
                cumulative_return=cumulative,
                drawdown=wealth / peak - ONE,
            )
        )
        previous_value = value

    return points


def daily_returns_of(points: list[ValuePoint]) -> list[Decimal]:
    return [point.daily_return for point in points if point.daily_return is not None]


def fill_from_transaction(
    *,
    on: date,
    security_id: UUID,
    ticker: str,
    transaction_type: str,
    quantity: Decimal,
    price: Decimal,
) -> Fill:
    return Fill(
        on=on,
        security_id=security_id,
        ticker=ticker,
        is_buy=transaction_type == TransactionType.BUY,
        quantity=quantity,
        price=price,
    )


def _mark_to_market(
    holdings: dict[UUID, Decimal],
    on: date,
    index: PriceIndex,
    fallback_price: dict[UUID, Decimal],
) -> Decimal | None:
    total = ZERO
    for security_id, quantity in holdings.items():
        price = index.on_or_before(security_id, on)
        if price is None:
            price = fallback_price.get(security_id)
        if price is None:
            return None
        total += quantity * price
    return total
