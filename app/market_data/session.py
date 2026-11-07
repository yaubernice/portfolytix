"""Whether the US cash session is open. Early closes are 13:00 New York."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.market_data.calendar import nth_weekday, us_market_holidays

NEW_YORK = ZoneInfo("America/New_York")
_OPEN = 9 * 60 + 30
_REGULAR_CLOSE = 16 * 60
_EARLY_CLOSE = 13 * 60


def us_early_closes(year: int) -> set[date]:
    """Common NYSE 13:00 closes. This is not the full exchange calendar."""
    days: set[date] = set()
    thanksgiving = nth_weekday(year, 11, 3, 4)
    days.add(thanksgiving + timedelta(days=1))
    july3 = date(year, 7, 3)
    if july3.weekday() < 5:
        days.add(july3)
    eve = date(year, 12, 24)
    if eve.weekday() < 5:
        days.add(eve)
    return days


def session_status(now: datetime | None = None) -> dict[str, object]:
    current = (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)
    day = current.date()
    minutes = current.hour * 60 + current.minute
    early = day in us_early_closes(day.year)
    closes = "13:00" if early else "16:00"
    base = {
        "as_of": current.isoformat(),
        "timezone": "America/New_York",
        "closes_at": closes,
    }
    if day.weekday() >= 5:
        return {**base, "open": False, "reason": "weekend"}
    if day in us_market_holidays(day.year, day.year):
        return {**base, "open": False, "reason": "holiday"}
    close_minute = _EARLY_CLOSE if early else _REGULAR_CLOSE
    if minutes < _OPEN or minutes >= close_minute:
        return {**base, "open": False, "reason": "hours"}
    return {**base, "open": True, "reason": "open"}
