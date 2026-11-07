from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import JobStatus, Price, Security, UniverseMembership
from app.jobs.market_data_job import update_market_data
from app.market_data.provider import MarketDataProvider
from app.market_data.types import RawBar
from app.market_data.universe import (
    apply_universe,
    parse_sp500_constituents,
    tickers_for_ingest,
)
from app.market_data.yahoo_history import YahooHistoryProvider

_CSV = """Symbol,Security,GICS Sector,GICS Sub-Industry
AAPL,Apple Inc.,Technology,Consumer Electronics
GOOGL,Alphabet Inc. Class A,Communication Services,Interactive Media
AAPL,Apple duplicate,Technology,Duplicate
,Missing,Technology,No ticker
NOPE,,Technology,No name
"""


class _Bars(MarketDataProvider):
    name = "fake"

    def __init__(self, close: str = "100") -> None:
        self.close = close
        self.calls: list[str] = []

    def fetch_daily_bars(self, ticker: str, start: date, end: date) -> list[RawBar]:
        self.calls.append(ticker)
        price = Decimal(self.close)
        return [
            RawBar(
                ticker=ticker,
                day=start,
                open=price,
                high=price,
                low=price,
                close=price,
                adjusted_close=price,
                volume=10,
            )
        ]


def test_constituent_csv_keeps_names_and_skips_bad_rows() -> None:
    rows = parse_sp500_constituents(_CSV)
    assert [(row.ticker, row.name, row.sector) for row in rows] == [
        ("AAPL", "Apple Inc.", "Technology"),
        ("GOOGL", "Alphabet Inc. Class A", "Communication Services"),
    ]
    assert rows[0].exchange == ""


def test_universe_import_is_idempotent_and_retires_without_deleting_prices(
    sqlite_session: Session,
) -> None:
    listings = parse_sp500_constituents(_CSV)
    first = apply_universe(sqlite_session, listings, universe="sp500")
    assert first.securities_inserted == 2
    assert first.memberships_upserted == 2
    apple = sqlite_session.scalar(select(Security).where(Security.ticker == "AAPL"))
    assert apple is not None
    sqlite_session.add(
        Price(
            security_id=apple.id,
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            adjusted_close=Decimal("10"),
            volume=1,
            source="yahoo",
        )
    )
    sqlite_session.flush()

    second = apply_universe(sqlite_session, listings, universe="sp500")
    assert second.securities_inserted == 0
    assert second.memberships_deactivated == 0
    assert sqlite_session.scalar(select(func.count()).select_from(Security)) == 2

    only_apple = [row for row in listings if row.ticker == "AAPL"]
    retired = apply_universe(sqlite_session, only_apple, universe="sp500")
    assert retired.memberships_deactivated == 1
    google = sqlite_session.scalar(
        select(UniverseMembership)
        .join(Security)
        .where(Security.ticker == "GOOGL")
    )
    assert google is not None
    assert google.active is False
    assert sqlite_session.scalar(select(func.count()).select_from(Price)) == 1
    assert sqlite_session.scalar(select(Security).where(Security.ticker == "GOOGL"))


def test_ambiguous_ticker_is_skipped(sqlite_session: Session) -> None:
    for provider in ("nasdaq", "other"):
        sqlite_session.add(
            Security(
                ticker="AAPL",
                name="Apple Inc.",
                exchange="NASDAQ",
                sector="Technology",
                currency="USD",
                provider=provider,
                provider_symbol="AAPL",
            )
        )
    sqlite_session.flush()
    report = apply_universe(
        sqlite_session,
        parse_sp500_constituents(_CSV),
        universe="sp500",
    )
    assert "AAPL" in report.skipped_tickers
    memberships = sqlite_session.scalar(
        select(func.count()).select_from(UniverseMembership)
    )
    assert memberships == 1


def test_universe_ingest_runs_with_zero_holdings(sqlite_session: Session) -> None:
    apply_universe(
        sqlite_session,
        parse_sp500_constituents(_CSV),
        universe="sp500",
    )
    provider = _Bars("101")
    run = update_market_data(
        sqlite_session,
        tickers=None,
        start=date(2024, 6, 3),
        end=date(2024, 6, 3),
        provider=provider,
        trigger="cli",
        universe="sp500",
        symbol_limit=10,
    )
    sqlite_session.flush()
    assert run.status == JobStatus.SUCCESS
    assert sorted(provider.calls) == ["AAPL", "GOOGL"]
    prices = list(sqlite_session.scalars(select(Price)))
    assert len(prices) == 2
    assert {row.close for row in prices} == {Decimal("101")}
    again = _Bars("102")
    update_market_data(
        sqlite_session,
        start=date(2024, 6, 3),
        end=date(2024, 6, 3),
        provider=again,
        trigger="cli",
        universe="sp500",
        symbol_limit=10,
    )
    sqlite_session.flush()
    sqlite_session.expire_all()
    stored = list(sqlite_session.scalars(select(Price)))
    assert again.calls
    assert len(stored) == 2
    assert {row.close for row in stored} == {Decimal("102")}


def test_empty_universe_does_not_call_the_provider(sqlite_session: Session) -> None:
    provider = _Bars()
    run = update_market_data(
        sqlite_session,
        start=date(2024, 6, 3),
        end=date(2024, 6, 3),
        provider=provider,
        trigger="cli",
        universe="sp500",
        symbol_limit=5,
    )
    assert run.status == JobStatus.SKIPPED
    assert run.error == "universe_empty:sp500"
    assert provider.calls == []
    assert tickers_for_ingest(sqlite_session, "sp500", 5) == []


class _Response:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _Client:
    def __init__(self) -> None:
        self.params: dict | None = None
        self.url = ""

    def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        del headers
        self.url = url
        self.params = params
        stamp = int(datetime(2024, 6, 3, 20, 0, tzinfo=UTC).timestamp())
        return _Response(
            {
                "chart": {
                    "result": [
                        {
                            "timestamp": [stamp],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [10],
                                        "high": [12],
                                        "low": [9],
                                        "close": [11],
                                        "volume": [100],
                                    }
                                ],
                                "adjclose": [{"adjclose": [10.5]}],
                            },
                        }
                    ]
                }
            }
        )


def test_yahoo_requests_the_asked_window_and_keeps_the_caller_ticker() -> None:
    client = _Client()
    bars = YahooHistoryProvider(client).fetch_daily_bars(
        "BRK.B",
        date(2024, 6, 3),
        date(2024, 6, 3),
    )
    assert client.url.endswith("/BRK-B")
    assert client.params is not None
    assert "period1" in client.params
    assert "period2" in client.params
    assert "range" not in client.params
    assert len(bars) == 1
    assert bars[0].ticker == "BRK.B"
    assert bars[0].adjusted_close == Decimal("10.5000")
    assert bars[0].day == date(2024, 6, 3)
