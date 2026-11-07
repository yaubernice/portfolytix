from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Price, Security
from app.main import app
from app.market_data.universe import apply_universe, parse_sp500_constituents

_CSV = """Symbol,Security,GICS Sector
AAPL,Apple Inc.,Technology
"""


def test_market_routes_do_not_require_a_portfolio(
    client: TestClient,
    sqlite_session: Session,
) -> None:
    apply_universe(
        sqlite_session,
        parse_sp500_constituents(_CSV),
        universe=settings.universe_code,
    )
    apple_id = sqlite_session.scalar(select(Security.id))
    assert apple_id is not None
    sqlite_session.add(
        Price(
            security_id=apple_id,
            timestamp=datetime(2024, 5, 31, tzinfo=UTC),
            open=Decimal("9"),
            high=Decimal("10"),
            low=Decimal("8"),
            close=Decimal("10"),
            adjusted_close=Decimal("10"),
            volume=4,
            source="yahoo",
        )
    )
    sqlite_session.add(
        Price(
            security_id=apple_id,
            timestamp=datetime(2024, 6, 3, tzinfo=UTC),
            open=Decimal("10"),
            high=Decimal("12"),
            low=Decimal("9"),
            close=Decimal("11"),
            adjusted_close=Decimal("11"),
            volume=5,
            source="yahoo",
        )
    )
    sqlite_session.commit()

    bare = TestClient(app)
    status = bare.get("/market/status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["provider"] == settings.market_data_provider
    assert body["active_members"] == 1
    assert body["last_bar_date"] == "2024-06-03"
    assert "not real-time" in body["note"]

    overview = bare.get("/market/overview")
    assert overview.status_code == 200, overview.text
    market = overview.json()
    assert market["covered_members"] == 1
    assert market["advancing"] == 1
    assert market["gainers"][0]["ticker"] == "AAPL"
    assert market["gainers"][0]["change_percent"] == "0.1"

    members = bare.get("/market/securities")
    assert members.status_code == 200, members.text
    page = members.json()
    assert page["total"] == 1
    assert page["items"][0]["ticker"] == "AAPL"
    assert page["items"][0]["latest_bar_date"] == "2024-06-03"

    prices = bare.get("/market/securities/AAPL/prices")
    assert prices.status_code == 200, prices.text
    bars = prices.json()
    assert bars["total"] == 2
    assert bars["items"][0]["close"] == "11"
    assert bars["items"][0]["source"] == "yahoo"
    assert bare.get("/market/securities/MSFT/prices").status_code == 404
    del client
