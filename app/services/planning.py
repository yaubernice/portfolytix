"""Goal math and a contribution split. Rates are assumptions, not forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")
ONE = Decimal("1")
SCENARIO_RATES = (ZERO, Decimal("0.04"), Decimal("0.08"))


@dataclass(frozen=True, slots=True)
class Scenario:
    annual_rate: Decimal
    future_value: Decimal
    monthly_contribution: Decimal


def months_between(today_ordinal_months: int, target_ordinal_months: int) -> int:
    return max(0, target_ordinal_months - today_ordinal_months)


def future_value(
    present: Decimal,
    monthly: Decimal,
    months: int,
    annual_rate: Decimal,
) -> Decimal:
    """Compound present value and add a level monthly contribution."""
    if months <= 0:
        return present
    if annual_rate == ZERO:
        return present + monthly * Decimal(months)
    monthly_rate = (ONE + annual_rate) ** (ONE / Decimal(12)) - ONE
    if monthly_rate == ZERO:
        return present + monthly * Decimal(months)
    growth = (ONE + monthly_rate) ** Decimal(months)
    deposits = monthly * (growth - ONE) / monthly_rate
    return present * growth + deposits


def scenarios(
    present: Decimal,
    monthly: Decimal,
    months: int,
    rates: tuple[Decimal, ...] = SCENARIO_RATES,
) -> list[Scenario]:
    return [
        Scenario(
            annual_rate=rate,
            future_value=future_value(present, monthly, months, rate),
            monthly_contribution=monthly,
        )
        for rate in rates
    ]


def required_monthly(
    present: Decimal,
    target: Decimal,
    months: int,
    annual_rate: Decimal,
) -> Decimal | None:
    """Level deposit that reaches ``target`` at one assumed rate."""
    if months <= 0:
        return None
    if annual_rate == ZERO:
        gap = target - present
        return gap / Decimal(months) if gap > ZERO else ZERO
    monthly_rate = (ONE + annual_rate) ** (ONE / Decimal(12)) - ONE
    growth = (ONE + monthly_rate) ** Decimal(months)
    annuity = (growth - ONE) / monthly_rate
    if annuity == ZERO:
        return None
    payment = (target - present * growth) / annuity
    return payment if payment > ZERO else ZERO


def contributed(monthly: Decimal, months: int) -> Decimal:
    return monthly * Decimal(months)


def shares_at_price(amount: Decimal, price: Decimal | None) -> Decimal | None:
    if price is None or price <= ZERO:
        return None
    return amount / price


def equal_weight_amounts(
    weights: list[tuple[str, Decimal]],
    amount: Decimal,
) -> list[tuple[str, Decimal]]:
    """Split ``amount`` toward an equal share of the holdings already listed.

    The target is 1/N of the current names. It is not a view on what to own.
    """
    count = len(weights)
    if count == 0 or amount <= ZERO:
        return []
    target = ONE / Decimal(count)
    gaps = [
        (ticker, target - weight)
        for ticker, weight in weights
        if weight < target
    ]
    total = sum((gap for _ticker, gap in gaps), ZERO)
    if total <= ZERO:
        return []
    return [
        (ticker, amount * gap / total)
        for ticker, gap in gaps
    ]


def buy_after_runup(
    fill_price: Decimal,
    earlier_close: Decimal | None,
    threshold: Decimal = Decimal("0.10"),
) -> bool | None:
    """True when the fill is at least ``threshold`` above an earlier close."""
    if earlier_close is None or earlier_close <= ZERO:
        return None
    return fill_price / earlier_close - ONE >= threshold
