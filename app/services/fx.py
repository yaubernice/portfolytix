"""USD cross rates for display conversion.

Rates are expressed as USD per one unit of the foreign currency
(the same convention as Yahoo ``EURUSD=X``). Missing rates stay out
of the map so the client can fall back to USD.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.market_data.errors import ProviderError
from app.market_data.yahoo_history import YAHOO_CHART, parse_yahoo_chart
from app.repositories.price_repository import PriceRepository
from app.repositories.security_repository import SecurityRepository

DISPLAY_CURRENCIES = (
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "HKD",
    "SGD",
    "CAD",
    "AUD",
    "CHF",
    "CNY",
    "INR",
    "KRW",
)


def fx_pair_ticker(currency: str) -> str:
    return f"{currency.upper()}USD=X"


def load_display_rates(session: Session) -> dict[str, Any]:
    securities = SecurityRepository(session)
    prices = PriceRepository(session)
    rates: dict[str, str] = {"USD": "1"}
    as_of: date | None = None
    sources: dict[str, str] = {"USD": "identity"}

    for code in DISPLAY_CURRENCIES:
        if code == "USD":
            continue
        stored = _stored_rate(securities, prices, code)
        if stored is not None:
            rate, on = stored
            rates[code] = format(rate, "f")
            sources[code] = "stored"
            as_of = on if as_of is None else max(as_of, on)
            continue
        fetched = _yahoo_rate(code)
        if fetched is not None:
            rate, on = fetched
            rates[code] = format(rate, "f")
            sources[code] = "yahoo"
            as_of = on if as_of is None else max(as_of, on)

    return {
        "base": "USD",
        "as_of": as_of.isoformat() if as_of else None,
        "rates": rates,
        "sources": sources,
        "note": (
            "Rates are USD per one unit of the listed currency "
            "(same as EURUSD=X). Portfolio figures are stored in USD "
            "and converted for display only."
        ),
    }


def _stored_rate(
    securities: SecurityRepository,
    prices: PriceRepository,
    currency: str,
) -> tuple[Decimal, date] | None:
    try:
        listing = securities.get_by_ticker(fx_pair_ticker(currency))
    except ConflictError:
        return None
    if listing is None:
        return None
    bar = prices.latest(listing.id)
    if bar is None or bar.adjusted_close is None or bar.adjusted_close <= 0:
        return None
    on = bar.timestamp.date() if hasattr(bar.timestamp, "date") else bar.timestamp
    return Decimal(bar.adjusted_close), on


def _yahoo_rate(currency: str) -> tuple[Decimal, date] | None:
    ticker = fx_pair_ticker(currency)
    end = date.today()
    start = end - timedelta(days=14)
    period1 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    period2 = int(datetime(end.year, end.month, end.day, tzinfo=UTC).timestamp()) + 86400
    try:
        response = httpx.get(
            YAHOO_CHART.format(symbol=ticker),
            params={"interval": "1d", "period1": period1, "period2": period2},
            timeout=12.0,
            headers={"User-Agent": "Portfolytix/1.0"},
            follow_redirects=True,
        )
        response.raise_for_status()
        bars = parse_yahoo_chart(response.json(), ticker, start, end)
    except (ProviderError, httpx.HTTPError, ValueError, TypeError):
        return None
    if not bars:
        return None
    bar = bars[-1]
    close = bar.adjusted_close or bar.close
    if close is None or close <= 0:
        return None
    return Decimal(close), bar.day
