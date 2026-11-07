"""In-process limit for failed sign-ins. A restart clears the counts."""

from __future__ import annotations

import time

_WINDOW_SECONDS = 15 * 60
_LIMIT = 8
_failures: dict[str, list[float]] = {}


def too_many_attempts(email: str, now: float | None = None) -> bool:
    stamp = time.monotonic() if now is None else now
    recent = [
        item
        for item in _failures.get(email, [])
        if stamp - item < _WINDOW_SECONDS
    ]
    _failures[email] = recent
    return len(recent) >= _LIMIT


def record_failure(email: str, now: float | None = None) -> None:
    stamp = time.monotonic() if now is None else now
    _failures.setdefault(email, []).append(stamp)


def clear_attempts(email: str) -> None:
    _failures.pop(email, None)
