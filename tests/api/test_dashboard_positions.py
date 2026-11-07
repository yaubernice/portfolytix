from fastapi.testclient import TestClient

from app.db.models import Security, User
from tests.api.helpers import create_portfolio


def test_dashboard_holding_without_a_price_is_not_zero(
    client: TestClient,
    user: User,
    apple: Security,
) -> None:
    portfolio = create_portfolio(client, user.id)
    bought = client.post(
        f"/portfolios/{portfolio['id']}/transactions",
        json={
            "ticker": apple.ticker,
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "150",
            "timestamp": "2026-01-02T15:00:00Z",
        },
    )
    assert bought.status_code == 201, bought.text

    positions = client.get(f"/portfolios/{portfolio['id']}/positions")
    assert positions.status_code == 200, positions.text
    body = positions.json()
    assert body["market_value"] is None
    assert body["cost_basis"] == "1500"
    assert body["positions"][0]["current_price"] is None
    assert body["positions"][0]["market_value"] is None

    analytics = client.get(f"/portfolios/{portfolio['id']}/analytics")
    assert analytics.status_code == 409
    assert "No price history" in analytics.text


def test_empty_portfolio_analytics_says_there_are_no_transactions(
    client: TestClient,
    user: User,
) -> None:
    portfolio = create_portfolio(client, user.id)
    analytics = client.get(f"/portfolios/{portfolio['id']}/analytics")
    assert analytics.status_code == 409
    assert "no transactions" in analytics.text
