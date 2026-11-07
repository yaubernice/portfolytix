"""Stored fund constituents from Yahoo's top-holdings module.

The response is unofficial and delayed. An empty or failed response
leaves the stored rows unchanged.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import httpx

_URL = (
    "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
    "?modules=topHoldings"
)


def fetch_top_holdings(ticker: str) -> list[tuple[str, Decimal]]:
    with httpx.Client(timeout=15.0, trust_env=False) as client:
        response = client.get(
            _URL.format(ticker=ticker),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()
    result = (payload.get("quoteSummary") or {}).get("result") or []
    if not result:
        return []
    holdings = (result[0].get("topHoldings") or {}).get("holdings") or []
    rows: list[tuple[str, Decimal]] = []
    for item in holdings:
        symbol = str(item.get("symbol") or "").upper().strip()
        raw = item.get("holdingPercent")
        if not symbol or raw is None:
            continue
        try:
            weight = Decimal(str(raw))
        except InvalidOperation:
            continue
        if weight > 1:
            weight = weight / Decimal(100)
        if weight <= 0:
            continue
        rows.append((symbol, weight))
    return rows
