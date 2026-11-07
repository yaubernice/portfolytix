from app.ai.grounding import figures_in_text_are_grounded


def test_supplied_figures_and_rounded_percents_pass() -> None:
    corpus = '{"total_return": "0.2141", "value": "12066.10"}'
    assert figures_in_text_are_grounded(
        "The stored return is 21.41% and the value is 12,066.10.",
        corpus,
    )


def test_a_figure_that_was_not_supplied_fails() -> None:
    assert not figures_in_text_are_grounded(
        "The portfolio returned 18% in 2024.",
        '{"total_return": "0.2141"}',
    )
