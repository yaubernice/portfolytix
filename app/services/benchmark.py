"""Stored-price comparisons. Missing closes stay missing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def indexed_returns(
    portfolio_dates: list[date],
    closes: dict[date, Decimal],
) -> list[tuple[date, Decimal]]:
    """Index an overlapping close series to the first shared date.

    The result is close / first close - 1. Dates without a stored close
    are omitted.
    """
    shared = [day for day in portfolio_dates if day in closes]
    if len(shared) < 2:
        return []
    base = closes[shared[0]]
    if base == 0:
        return []
    return [(day, closes[day] / base - 1) for day in shared]


def pearson(pairs: list[tuple[Decimal, Decimal]]) -> Decimal | None:
    """Sample correlation. Fewer than five pairs is not a figure."""
    count = len(pairs)
    if count < 5:
        return None
    xs = [left for left, _right in pairs]
    ys = [right for _left, right in pairs]
    mean_x = sum(xs, Decimal("0")) / count
    mean_y = sum(ys, Decimal("0")) / count
    numerator = sum(
        ((x - mean_x) * (y - mean_y) for x, y in pairs),
        Decimal("0"),
    )
    var_x = sum(((x - mean_x) ** 2 for x in xs), Decimal("0"))
    var_y = sum(((y - mean_y) ** 2 for y in ys), Decimal("0"))
    if var_x == 0 or var_y == 0:
        return None
    value = numerator / (var_x.sqrt() * var_y.sqrt())
    return value.quantize(Decimal("0.0001"))


def beta(pairs: list[tuple[Decimal, Decimal]]) -> Decimal | None:
    """Sample beta of the first series versus the second.

    Each pair is (portfolio return, benchmark return). Fewer than five
    pairs is not a figure.
    """
    count = len(pairs)
    if count < 5:
        return None
    ys = [left for left, _right in pairs]
    xs = [right for _left, right in pairs]
    mean_x = sum(xs, Decimal("0")) / count
    mean_y = sum(ys, Decimal("0")) / count
    covariance = sum(
        ((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)),
        Decimal("0"),
    ) / Decimal(count - 1)
    var_x = sum(((x - mean_x) ** 2 for x in xs), Decimal("0")) / Decimal(count - 1)
    if var_x == 0:
        return None
    return (covariance / var_x).quantize(Decimal("0.0001"))


def daily_pairs(
    left: dict[date, Decimal],
    right: dict[date, Decimal],
) -> list[tuple[Decimal, Decimal]]:
    """Aligned daily returns for the shared dates."""
    shared = sorted(set(left) & set(right))
    return [(left[day], right[day]) for day in shared]


def pairwise_correlations(
    series: dict[str, dict[date, Decimal]],
) -> list[tuple[str, str, Decimal | None, int]]:
    """Upper triangle of ticker pairs. Missing cells stay None."""
    names = sorted(series)
    rows: list[tuple[str, str, Decimal | None, int]] = []
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            pairs = daily_pairs(series[left], series[right])
            rows.append((left, right, pearson(pairs), len(pairs)))
    return rows
