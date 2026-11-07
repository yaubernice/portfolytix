"""Income figures that use only stored cash and a stored yield."""

from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0")
# More than 365 days. This is a label, not a tax determination.
LONG_HOLDING_DAYS = 365


def holding_term(held_days: int) -> str:
    return "long" if held_days > LONG_HOLDING_DAYS else "short"


def yield_on_cost(
    income: Decimal | None,
    cost_basis: Decimal | None,
) -> Decimal | None:
    if income is None or cost_basis is None or cost_basis <= ZERO:
        return None
    return income / cost_basis


def projected_income(
    pairs: list[tuple[Decimal, Decimal | None]],
) -> Decimal | None:
    """Market value times a stored dividend yield. Missing yields are skipped."""
    total = ZERO
    found = False
    for value, rate in pairs:
        if rate is None:
            continue
        total += value * rate
        found = True
    return total if found else None


def fund_expense(
    pairs: list[tuple[Decimal, Decimal | None]],
) -> Decimal | None:
    """Market value times a stored expense ratio. A missing ratio stays unset."""
    total = ZERO
    found = False
    for value, rate in pairs:
        if rate is None:
            continue
        total += value * rate
        found = True
    return total if found else None
