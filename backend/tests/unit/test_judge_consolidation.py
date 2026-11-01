from decimal import Decimal

import pytest

from tkd_scorer.domain.entities.common import AthleteSide
from tkd_scorer.domain.services.judge_consolidation import (
    consolidate_scorecards,
    consolidate_scores,
    consolidated_score_for_judges,
    resolve_winner,
    winner_side,
)
from tkd_scorer.domain.services.judge_scorecard import JudgeScorecard, RoundScore


def test_consolidated_score_for_3_judges_uses_average() -> None:
    result = consolidated_score_for_judges(
        [Decimal("9.8"), Decimal("9.7"), Decimal("9.9")],
        judges_required=3,
    )
    assert result == Decimal("9.80")


def test_consolidated_score_for_5_judges_discards_min_max() -> None:
    result = consolidated_score_for_judges(
        [Decimal("9.5"), Decimal("9.9"), Decimal("9.8"), Decimal("9.7"), Decimal("9.6")],
        judges_required=5,
    )
    assert result == Decimal("9.70")


def test_consolidated_score_for_7_judges_discards_min_max() -> None:
    result = consolidated_score_for_judges(
        [
            Decimal("9.3"),
            Decimal("9.8"),
            Decimal("9.6"),
            Decimal("9.9"),
            Decimal("9.7"),
            Decimal("9.4"),
            Decimal("9.5"),
        ],
        judges_required=7,
    )
    assert result == Decimal("9.60")


@pytest.mark.parametrize(
    ("judges_required", "scores", "expected"),
    [
        (1, [Decimal("9.8")], Decimal("9.80")),
        (2, [Decimal("9.8"), Decimal("9.6")], Decimal("9.70")),
        (4, [Decimal("9.9"), Decimal("9.8"), Decimal("9.7"), Decimal("9.6")], Decimal("9.75")),
        (6, [Decimal("9.9"), Decimal("9.8"), Decimal("9.7"), Decimal("9.6"), Decimal("9.5"), Decimal("9.4")], Decimal("9.65")),
    ],
)
def test_consolidated_score_supports_test_judge_counts(
    judges_required: int,
    scores: list[Decimal],
    expected: Decimal,
) -> None:
    result = consolidated_score_for_judges(scores, judges_required=judges_required)
    assert result == expected


def test_winner_side_detects_draw() -> None:
    assert winner_side(Decimal("9.75"), Decimal("9.75")) == "draw"


def test_winner_side_red_wins_with_higher_score() -> None:
    assert winner_side(Decimal("9.81"), Decimal("9.79")) == "red"


def test_winner_side_blue_wins_with_higher_score() -> None:
    assert winner_side(Decimal("9.62"), Decimal("9.77")) == "blue"


def _card(session_id: str, rounds: list[tuple[int, str, str, str, str]]) -> JudgeScorecard:
    return JudgeScorecard(
        session_id=session_id,
        judge_name=session_id,
        rounds=tuple(
            RoundScore(
                round_number=number,
                technique_red=Decimal(tec_red),
                presentation_red=Decimal(pres_red),
                technique_blue=Decimal(tec_blue),
                presentation_blue=Decimal(pres_blue),
            )
            for number, tec_red, pres_red, tec_blue, pres_blue in rounds
        ),
        total_events=0,
        last_sequence=0,
    )


def test_consolidate_scores_uses_mean_for_3_and_trimmed_mean_for_5_and_7() -> None:
    assert consolidate_scores([Decimal("3.1"), Decimal("2.9"), Decimal("3.4")]) == Decimal("3.13")
    assert consolidate_scores(
        [Decimal("2.9"), Decimal("3.1"), Decimal("3.0"), Decimal("3.4"), Decimal("2.5")]
    ) == Decimal("3.00")
    assert consolidate_scores(
        [Decimal(value) for value in ("5.0", "5.4", "4.1", "5.9", "5.2", "5.3", "5.1")]
    ) == Decimal("5.20")


def test_worked_example_five_judges_trims_technique_and_presentation_separately() -> None:
    technique = ["2.9", "3.1", "3.0", "3.4", "2.5"]
    presentation = ["5.2", "5.0", "5.6", "4.8", "5.1"]
    cards = [
        _card(f"sess-{index}", [(1, tec, pres, "4.0", "6.0")])
        for index, (tec, pres) in enumerate(zip(technique, presentation, strict=True))
    ]

    result = consolidate_scorecards(cards)
    round_one = result.round(1)

    assert round_one is not None
    assert round_one.judges_count == 5
    assert round_one.technique_red == Decimal("3.00")
    assert round_one.presentation_red == Decimal("5.10")
    assert round_one.score_red == Decimal("8.10")
    assert result.score_red == Decimal("8.10")


def test_match_score_is_the_two_decimal_mean_of_the_round_scores() -> None:
    cards = [
        _card("sess-1", [(1, "3.6", "5.8", "3.9", "6.0"), (2, "3.5", "5.7", "3.7", "5.9")]),
        _card("sess-2", [(1, "3.8", "5.6", "3.6", "5.8"), (2, "3.9", "6.0", "3.8", "5.5")]),
        _card("sess-3", [(1, "3.6", "5.8", "3.8", "6.0"), (2, "3.7", "5.8", "3.9", "5.7")]),
    ]

    result = consolidate_scorecards(cards)

    assert result.round(1).technique_red == Decimal("3.67")
    assert result.round(1).presentation_red == Decimal("5.73")
    assert result.round(1).score_red == Decimal("9.40")
    assert result.round(2).score_red == Decimal("9.53")
    assert result.score_red == Decimal("9.47")
    assert result.score_blue == Decimal("9.60")
    assert result.winner == "blue"


def test_rounds_are_consolidated_with_the_judges_that_scored_them() -> None:
    cards = [
        _card("sess-1", [(1, "3.0", "5.0", "4.0", "6.0"), (2, "3.5", "5.5", "4.0", "6.0")]),
        _card("sess-2", [(1, "3.2", "5.2", "4.0", "6.0")]),
    ]

    result = consolidate_scorecards(cards)

    assert result.round(1).judges_count == 2
    assert result.round(2).judges_count == 1
    assert result.round(2).technique_red == Decimal("3.50")


def test_tie_on_match_score_is_broken_by_consolidated_presentation() -> None:
    assert (
        resolve_winner(
            score_red=Decimal("9.10"),
            score_blue=Decimal("9.10"),
            presentation_red=Decimal("10.60"),
            presentation_blue=Decimal("10.80"),
        )
        == "blue"
    )
    assert (
        resolve_winner(
            score_red=Decimal("9.10"),
            score_blue=Decimal("9.10"),
            presentation_red=Decimal("10.80"),
            presentation_blue=Decimal("10.80"),
        )
        == "rematch"
    )
    assert (
        resolve_winner(
            score_red=Decimal("9.11"),
            score_blue=Decimal("9.10"),
            presentation_red=Decimal("1.00"),
            presentation_blue=Decimal("12.00"),
        )
        == "red"
    )


def test_consolidated_match_winner_uses_presentation_tie_break() -> None:
    cards = [_card("sess-1", [(1, "3.0", "6.0", "3.5", "5.5")])]

    result = consolidate_scorecards(cards)

    assert result.score_red == result.score_blue == Decimal("9.00")
    assert result.winner == "red"


def test_tie_break_order_score_then_presentation_then_all_judges_then_rematch() -> None:
    tied = {"score_red": Decimal("9.10"), "score_blue": Decimal("9.10")}
    # Step 1: match score decides even when the later steps say otherwise.
    assert (
        resolve_winner(
            score_red=Decimal("9.20"),
            score_blue=Decimal("9.10"),
            presentation_red=Decimal("1.00"),
            presentation_blue=Decimal("9.00"),
            all_judges_red=Decimal("1.00"),
            all_judges_blue=Decimal("99.00"),
        )
        == "red"
    )
    # Step 2: higher consolidated presentation.
    assert (
        resolve_winner(
            **tied,
            presentation_red=Decimal("10.80"),
            presentation_blue=Decimal("10.60"),
            all_judges_red=Decimal("1.00"),
            all_judges_blue=Decimal("99.00"),
        )
        == "red"
    )
    # Step 3: higher sum of every judge's scores, dropped ones included.
    assert (
        resolve_winner(
            **tied,
            presentation_red=Decimal("10.80"),
            presentation_blue=Decimal("10.80"),
            all_judges_red=Decimal("136.40"),
            all_judges_blue=Decimal("136.50"),
        )
        == "blue"
    )
    # Still equal: rematch.
    assert (
        resolve_winner(
            **tied,
            presentation_red=Decimal("10.80"),
            presentation_blue=Decimal("10.80"),
            all_judges_red=Decimal("136.50"),
            all_judges_blue=Decimal("136.50"),
        )
        == "rematch"
    )


def test_all_judges_sum_includes_the_dropped_highest_and_lowest() -> None:
    # Five judges: the trimmed means are equal (technique 3.50, presentation 6.00 on both sides) but red's
    # dropped highest is lower, so the sum of all the judges' scores favours blue.
    red_technique = ["3.0", "3.5", "3.5", "3.5", "3.9"]
    blue_technique = ["3.4", "3.5", "3.5", "3.5", "3.6"]
    cards = [
        _card(f"sess-{index}", [(1, red, "6.0", blue, "6.0")])
        for index, (red, blue) in enumerate(zip(red_technique, blue_technique, strict=True))
    ]

    result = consolidate_scorecards(cards)

    assert result.score_red == result.score_blue == Decimal("9.50")
    assert result.presentation_total(AthleteSide.RED) == result.presentation_total(AthleteSide.BLUE)
    assert result.all_judges_total(AthleteSide.RED) == Decimal("47.40")
    assert result.all_judges_total(AthleteSide.BLUE) == Decimal("47.50")
    assert result.winner == "blue"


def test_identical_scorecards_require_a_rematch() -> None:
    cards = [_card(f"sess-{index}", [(1, "3.5", "6.0", "3.5", "6.0")]) for index in range(3)]

    assert consolidate_scorecards(cards).winner == "rematch"


def test_rematch_has_its_own_winner_label() -> None:
    from tkd_scorer.application.use_cases.admin_view_use_cases import AdminViewUseCases

    assert AdminViewUseCases._winner_label_key("rematch") == "winner.rematch"
    assert AdminViewUseCases._winner_label_key("red") == "winner.red"
