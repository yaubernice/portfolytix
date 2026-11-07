"""Reject a model sentence that introduces a figure it was not given."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NUMBER = re.compile(
    r"(?<![\w.])(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|-?\d+(?:\.\d+)?%?)(?![\w.])"
)


def figures_in_text_are_grounded(text: str, corpus: str) -> bool:
    """Every number in ``text`` must appear in ``corpus`` or round one that does."""
    for token in _NUMBER.findall(text):
        if not _token_allowed(token, corpus):
            return False
    return True


def _token_allowed(token: str, corpus: str) -> bool:
    if token in corpus:
        return True
    plain = token.replace(",", "")
    if plain in corpus:
        return True
    bare = plain[:-1] if plain.endswith("%") else plain
    if bare in corpus:
        return True
    try:
        shown = Decimal(bare)
    except InvalidOperation:
        return False
    for raw in re.findall(r"-?\d+(?:\.\d+)?", corpus.replace(",", "")):
        try:
            found = Decimal(raw)
        except InvalidOperation:
            continue
        if _matches(shown, found):
            return True
        if plain.endswith("%") and _matches(shown / Decimal(100), found):
            return True
        if _matches(shown, found * Decimal(100)):
            return True
    return False


def _matches(shown: Decimal, source: Decimal) -> bool:
    if shown == source:
        return True
    text = format(shown, "f")
    places = len(text.split(".")[1]) if "." in text else 0
    quantum = Decimal("1").scaleb(-places)
    return source.quantize(quantum) == shown
