"""Expand a fund only when its constituents are already stored."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class Constituent:
    ticker: str
    weight: Decimal


@dataclass(frozen=True, slots=True)
class LookLine:
    ticker: str
    direct_weight: Decimal
    look_through_weight: Decimal


def look_through(
    holdings: list[tuple[str, Decimal]],
    constituents: dict[str, list[Constituent]],
) -> tuple[list[LookLine], list[str]]:
    """Combine direct weights with stored fund weights.

    A fund with no stored constituents stays as one line. Weights that
    do not add to 1 stay on the fund rather than being invented.
    """
    direct = {ticker: weight for ticker, weight in holdings}
    combined: dict[str, Decimal] = {}
    notes: list[str] = []
    any_parts = False
    for ticker, weight in holdings:
        parts = constituents.get(ticker) or []
        if not parts:
            combined[ticker] = combined.get(ticker, ZERO) + weight
            continue
        any_parts = True
        covered = sum((part.weight for part in parts), ZERO)
        for part in parts:
            combined[part.ticker] = (
                combined.get(part.ticker, ZERO) + weight * part.weight
            )
        remainder = weight * (ONE - covered)
        if remainder > Decimal("0.001"):
            combined[ticker] = combined.get(ticker, ZERO) + remainder
            shown = (covered * Decimal(100)).quantize(Decimal("0.1"))
            notes.append(
                f"{ticker} stored constituents cover {shown}%. "
                "The rest stays on the fund."
            )
    if not any_parts:
        notes.append(
            "No fund constituents are stored, so each holding stays as itself."
        )
    rows = [
        LookLine(
            ticker=ticker,
            direct_weight=direct.get(ticker, ZERO),
            look_through_weight=weight,
        )
        for ticker, weight in combined.items()
        if weight != ZERO
    ]
    rows.sort(key=lambda row: (-row.look_through_weight, row.ticker))
    return rows, notes
