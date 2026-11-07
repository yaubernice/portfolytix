from decimal import Decimal

from app.services.research_service import _points, _rank_note, commentary_names_only


def test_commentary_rejects_a_company_that_was_not_supplied() -> None:
    text = "AAPL and MSFT have strong earnings, unlike the names listed."
    assert commentary_names_only(text, {"AUDC", "NVDA"}) is False


def test_commentary_allows_the_supplied_names() -> None:
    text = "AUDC is a smaller company. NVDA is already a large share."
    assert commentary_names_only(text, {"AUDC", "NVDA"}) is True


def test_overweight_sector_is_not_described_as_a_reason_to_add_more() -> None:
    points = _points(
        "Technology",
        Decimal("0.434"),
        Decimal("0.04"),
        Decimal("42"),
        Decimal("268000000"),
        True,
        True,
    )
    text = " ".join(points)
    assert "adds to that concentration" in text
    assert "not because the portfolio needs more of this sector" in text
    assert "A reason to look" not in text


def test_rank_note_explains_why_a_smaller_company_can_be_first() -> None:
    note = _rank_note(0, "small")
    assert "Idea 1" in note
    assert "small group" in note
    assert "smaller company can appear first" in note
