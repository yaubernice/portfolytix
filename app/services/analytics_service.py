from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import CacheBackend, NullCache
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import CashMovement, Security, ShareSplit, Transaction
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.price_repository import PriceRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.analytics import (
    AllocationOut,
    AnalyticsAssumptions,
    AnalyticsOut,
    BenchmarkPoint,
    CorrelationOut,
    PairCorrelationOut,
    SeriesPoint,
)
from app.services.analytics import (
    CloseBar,
    Split,
    allocation,
    annualized_return,
    annualized_volatility,
    build_value_series,
    daily_returns_of,
    external_cash_flows,
    fill_from_transaction,
    max_drawdown,
    sharpe_ratio,
    total_return,
)
from app.services.benchmark import (
    beta,
    daily_pairs,
    indexed_returns,
    pairwise_correlations,
    pearson,
)
from app.services.holdings import PositionLeg, aggregate_positions
from app.services.ledger_service import usd_amount
from app.services.reference_service import fill_daily_history

ANALYTICS_CACHE_SCHEMA = "v6"
# About one trading year. Fewer stored closes make an annualized
# volatility figure too sensitive to a handful of days.
_HISTORY_FLOOR = 200


class AnalyticsService:
    def __init__(
        self,
        session: Session,
        user_id: UUID,
        cache: CacheBackend | None = None,
    ) -> None:
        self.user_id = user_id
        self.portfolios = PortfolioRepository(session)
        self.transactions = TransactionRepository(session)
        self.prices = PriceRepository(session)
        self.cache = cache or NullCache()

    def get_analytics(self, portfolio_id: UUID) -> AnalyticsOut:
        if self.portfolios.get_owned(portfolio_id, self.user_id) is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")

        cache_key = self._cache_key(portfolio_id)
        cached = self.cache.get_json(cache_key)
        if isinstance(cached, dict):
            return AnalyticsOut.model_validate(cached)

        result = self._calculate(portfolio_id)
        self.cache.set_json(
            cache_key,
            result.model_dump(mode="json"),
            settings.analytics_cache_ttl_seconds,
        )
        return result

    def _calculate(self, portfolio_id: UUID) -> AnalyticsOut:
        rows = self.transactions.list_for_portfolio(portfolio_id)
        if not rows:
            raise ConflictError("Portfolio has no transactions")

        fills = [_fill(row) for row in rows]
        if settings.portfolio_history_backfill:
            self._backfill_short_history(rows)
        security_ids = list({fill.security_id for fill in fills})
        bars = [
            CloseBar(security_id=sid, on=_as_utc_date(ts), close=close)
            for sid, ts, close in self.prices.list_closes(security_ids)
        ]
        if not bars:
            raise ConflictError("No price history for portfolio holdings")

        points = build_value_series(
            fills,
            bars,
            self._external_cash(portfolio_id),
            self._splits(portfolio_id),
        )
        returns = daily_returns_of(points)
        rf = settings.risk_free_rate
        periods = settings.trading_days_per_year

        holdings = aggregate_positions(
            [
                PositionLeg(
                    security_id=row.security_id,
                    ticker=row.security.ticker,
                    transaction_type=row.transaction_type,
                    quantity=row.quantity,
                )
                for row in rows
            ]
        )
        quantities = {item.security_id: item.quantity for item in holdings}
        tickers = {item.security_id: item.ticker for item in holdings}
        latest = _with_live_marks(tickers, _latest_marks(bars))
        alloc = allocation(quantities, tickers, latest)

        start = points[0].on if points else None
        end = points[-1].on if points else None
        benchmark, benchmark_return, benchmark_beta = self._benchmark(points)
        return AnalyticsOut(
            portfolio_id=portfolio_id,
            start_date=start,
            end_date=end,
            observation_count=len(returns),
            total_return=total_return(returns) if returns else None,
            annualized_return=annualized_return(returns, periods),
            volatility=annualized_volatility(returns, periods),
            sharpe_ratio=sharpe_ratio(returns, rf, periods),
            max_drawdown=max_drawdown(returns) if returns else None,
            allocation=[
                AllocationOut(
                    security_id=line.security_id,
                    ticker=line.ticker,
                    quantity=line.quantity,
                    price=line.price,
                    market_value=line.market_value,
                    weight=line.weight,
                )
                for line in alloc
            ],
            series=[
                SeriesPoint(
                    date=point.on,
                    value=point.value,
                    cash_flow=point.cash_flow,
                    daily_pl=point.daily_pl,
                    daily_return=point.daily_return,
                    cumulative_return=point.cumulative_return,
                    drawdown=point.drawdown,
                )
                for point in points
            ],
            benchmark_ticker="SPY" if benchmark else None,
            benchmark_return=benchmark_return,
            benchmark_beta=benchmark_beta,
            benchmark=benchmark,
            correlations=_correlations(bars, points, tickers),
            correlation_pairs=_pair_correlations(bars, tickers),
            assumptions=_assumptions(rf, periods),
        )

    def _benchmark(
        self,
        points,
    ) -> tuple[list[BenchmarkPoint], Decimal | None, Decimal | None]:
        if len(points) < 2:
            return [], None, None
        spy = self.portfolios.session.scalar(
            select(Security)
            .where(Security.ticker == "SPY", Security.is_active.is_(True))
            .limit(1)
        )
        if spy is None:
            return [], None, None
        closes = {
            _as_utc_date(ts): close
            for _sid, ts, close in self.prices.list_closes([spy.id])
        }
        indexed = indexed_returns([point.on for point in points], closes)
        if len(indexed) < 2:
            return [], None, None
        portfolio_returns = {
            point.on: point.daily_return
            for point in points
            if point.daily_return is not None
        }
        spy_returns: dict[date, Decimal] = {}
        ordered = sorted(closes)
        for previous, current in zip(ordered, ordered[1:]):
            if closes[previous] == 0:
                continue
            spy_returns[current] = closes[current] / closes[previous] - 1
        return (
            [
                BenchmarkPoint(date=day, indexed_return=value)
                for day, value in indexed
            ],
            indexed[-1][1],
            beta(daily_pairs(portfolio_returns, spy_returns)),
        )

    def _backfill_short_history(self, rows: list[Transaction]) -> None:
        seen: set[UUID] = set()
        for row in rows:
            if row.security_id in seen:
                continue
            seen.add(row.security_id)
            if self.prices.count_for_security(row.security_id) >= _HISTORY_FLOOR:
                continue
            fill_daily_history(self.portfolios.session, row.security.ticker)

    def _external_cash(self, portfolio_id: UUID) -> list[tuple[date, Decimal]]:
        rows = self.portfolios.session.scalars(
            select(CashMovement).where(CashMovement.portfolio_id == portfolio_id)
        )
        prepared: list[tuple[date, str, Decimal]] = []
        for row in rows:
            usd = usd_amount(row.amount, row.currency, row.fx_rate)
            if usd is None:
                continue
            prepared.append((_as_utc_date(row.timestamp), row.kind, usd))
        return external_cash_flows(prepared)

    def _splits(self, portfolio_id: UUID) -> list[Split]:
        rows = self.portfolios.session.scalars(
            select(ShareSplit).where(ShareSplit.portfolio_id == portfolio_id)
        )
        return [
            Split(
                on=_as_utc_date(row.timestamp),
                security_id=row.security_id,
                numerator=Decimal(row.numerator),
                denominator=Decimal(row.denominator),
            )
            for row in rows
        ]

    def _cache_key(self, portfolio_id: UUID) -> str:
        portfolio_version = self.cache.get_version(f"portfolio:{portfolio_id}")
        prices_version = self.cache.get_version("prices")
        return (
            f"portfolio:{portfolio_id}:analytics:{ANALYTICS_CACHE_SCHEMA}:"
            f"portfolio-v{portfolio_version}:prices-v{prices_version}"
        )


def _fill(row: Transaction):
    return fill_from_transaction( #row = SQLAlchemy Transaction object
        on=_as_utc_date(row.timestamp),
        security_id=row.security_id,
        ticker=row.security.ticker,
        transaction_type=row.transaction_type,
        quantity=row.quantity,
        price=row.price,
    )


def _as_utc_date(value: datetime) -> date: #convert datetime to date
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(UTC).date()


def _with_live_marks(
    tickers: dict[UUID, str],
    marks: dict[UUID, Decimal],
) -> dict[UUID, Decimal]:
    """Current allocation uses the same quote as the positions table.

    Stored closes still build the return series. A quote miss keeps the close.
    """
    if not settings.provider_marks or not tickers:
        return marks
    try:
        from app.quotes.provider_marks import provider_quotes

        quotes = provider_quotes(list(tickers.values()))
    except Exception:
        return marks
    by_ticker = {ticker: security_id for security_id, ticker in tickers.items()}
    updated = dict(marks)
    for ticker, quote in quotes.items():
        security_id = by_ticker.get(ticker)
        if security_id is None or quote.price is None:
            continue
        updated[security_id] = quote.price
    return updated


def _return_series(bars) -> dict[UUID, dict[date, Decimal]]:
    history: dict[UUID, list[tuple[date, Decimal]]] = {}
    for bar in bars:
        history.setdefault(bar.security_id, []).append((bar.on, bar.close))
    series: dict[UUID, dict[date, Decimal]] = {}
    for security_id, closes in history.items():
        ordered = sorted(closes)
        daily: dict[date, Decimal] = {}
        for previous, current in zip(ordered, ordered[1:]):
            if previous[1] == 0:
                continue
            daily[current[0]] = current[1] / previous[1] - 1
        series[security_id] = daily
    return series


def _correlations(bars, points, tickers: dict[UUID, str]) -> list[CorrelationOut]:
    portfolio = {
        point.on: point.daily_return
        for point in points
        if point.daily_return is not None
    }
    series = _return_series(bars)
    rows: list[CorrelationOut] = []
    for security_id, ticker in sorted(tickers.items(), key=lambda item: item[1]):
        pairs = daily_pairs(series.get(security_id, {}), portfolio)
        rows.append(
            CorrelationOut(
                ticker=ticker,
                observations=len(pairs),
                value=pearson(pairs),
            )
        )
    return rows


def _pair_correlations(bars, tickers: dict[UUID, str]) -> list[PairCorrelationOut]:
    by_id = _return_series(bars)
    named = {
        ticker: by_id.get(security_id, {})
        for security_id, ticker in tickers.items()
    }
    return [
        PairCorrelationOut(
            left=left,
            right=right,
            observations=count,
            value=value,
        )
        for left, right, value, count in pairwise_correlations(named)
    ]


def _latest_marks(bars: list[CloseBar]) -> dict[UUID, Decimal]:
    latest: dict[UUID, Decimal] = {}
    for bar in bars:
        latest[bar.security_id] = bar.close
    return latest


def _assumptions(risk_free_rate: Decimal, periods: int) -> AnalyticsAssumptions:
    return AnalyticsAssumptions(
        method="time_weighted",
        price_field="adjusted_close",
        risk_free_rate_annual=risk_free_rate,
        trading_days_per_year=periods,
        return_frequency="daily",
        volatility="sample_stdev(daily_twr) * sqrt(trading_days_per_year)",
        sharpe="(mean(daily_twr) - rf/trading_days) / stdev(daily_twr)",
        max_drawdown="min(wealth / running_peak - 1) on TWR wealth index",
        cash_treatment=(
            "Buys and sells are external flows. Deposits and withdrawals "
            "stay in the value and are stripped from the return. Dividend "
            "cash is not added again, because closes are adjusted."
        ),
        disclaimer="Not investment advice. Teaching calculations only.",
    )
