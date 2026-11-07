from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_data.session import session_status

NEW_YORK = ZoneInfo("America/New_York")


def test_thanksgiving_2026_is_closed() -> None:
    status = session_status(datetime(2026, 11, 26, 11, 0, tzinfo=NEW_YORK))
    assert status["open"] is False
    assert status["reason"] == "holiday"


def test_day_after_thanksgiving_closes_at_1300() -> None:
    morning = session_status(datetime(2026, 11, 27, 11, 0, tzinfo=NEW_YORK))
    afternoon = session_status(datetime(2026, 11, 27, 14, 0, tzinfo=NEW_YORK))
    assert morning["open"] is True
    assert morning["closes_at"] == "13:00"
    assert afternoon["open"] is False
    assert afternoon["reason"] == "hours"
