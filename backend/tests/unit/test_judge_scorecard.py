from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tkd_scorer.domain.entities.common import AthleteSide, ScoreTarget
from tkd_scorer.domain.entities.score_event import ScoreEvent
from tkd_scorer.domain.exceptions.errors import ValidationError
from tkd_scorer.domain.services.judge_scorecard import (
    build_judge_scorecard,
    judge_aliases,
    parse_score_target,
)

_AT = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)


def _event(
    sequence: int,
    *,
    session_id: str = "sess-a",
    round_number: int = 1,
    side: AthleteSide = AthleteSide.RED,
    target: ScoreTarget = ScoreTarget.TECHNIQUE,
    delta: str = "-0.1",
) -> ScoreEvent:
    return ScoreEvent(
        id=f"{session_id}-{sequence}",
        idempotency_key=f"{session_id}-{sequence}",
        event_id=f"{session_id}-{sequence}",
        session_id=session_id,
        station_id="station-01",
        match_id="match-1",
        round_number=round_number,
        athlete_side=side,
        score_delta=Decimal(delta),
        score_before=Decimal("0"),
        score_after=Decimal("0"),
        occurred_at=_AT,
        sequence=sequence,
        judge_name=session_id,
        received_at=_AT,
        processed_at=_AT,
        score_target=target,
    )


def _scorecard(events: list[ScoreEvent], rounds: list[int], session_id: str = "sess-a"):
    return build_judge_scorecard(
        session_id=session_id,
        judge_name="Judge A",
        events=events,
        round_numbers=rounds,
        technique_start=Decimal("4.0"),
        presentation_category_start=Decimal("2.0"),
    )


def test_scorecard_separates_technique_and_each_presentation_category() -> None:
    events = [
        _event(1, delta="-0.3"),
        _event(2, target=ScoreTarget.PRESENTATION_SPEED_POWER, delta="-0.2"),
        _event(3, target=ScoreTarget.PRESENTATION_RHYTHM_TEMPO, delta="-0.1"),
        _event(4, side=AthleteSide.BLUE, delta="-0.1"),
        _event(5, side=AthleteSide.BLUE, target=ScoreTarget.PRESENTATION_ENERGY_EXPRESSION, delta="-0.4"),
        _event(6, delta="-0.1"),
    ]

    card = _scorecard(events, [1])
    round_one = card.round(1)

    assert round_one is not None
    assert round_one.technique_red == Decimal("3.6")
    assert round_one.presentation_red == Decimal("5.7")
    assert round_one.technique_blue == Decimal("3.9")
    assert round_one.presentation_blue == Decimal("5.6")
    assert card.total_events == 6
    assert card.last_sequence == 6


def test_scorecard_clamps_cumulatively_in_sequence_order_like_the_app() -> None:
    events = [
        # Technique: 4.0 -> 4.0 (capped at the start) -> 3.7 -> 3.8 (out-of-order arrival, sequence wins).
        _event(2, delta="-0.3"),
        _event(1, delta="+0.3"),
        _event(3, delta="+0.1"),
        # Speed and power: 2.0 -> 0.0 (floor) -> 0.3.
        _event(4, target=ScoreTarget.PRESENTATION_SPEED_POWER, delta="-2.5"),
        _event(5, target=ScoreTarget.PRESENTATION_SPEED_POWER, delta="+0.3"),
        # Rhythm and tempo: capped at 2.0.
        _event(6, target=ScoreTarget.PRESENTATION_RHYTHM_TEMPO, delta="+0.5"),
    ]

    round_one = _scorecard(events, [1]).round(1)

    assert round_one is not None
    assert round_one.technique_red == Decimal("3.8")
    assert round_one.presentation_red == Decimal("4.3")


def test_scorecard_ignores_other_judges_and_uses_start_values_for_rounds_without_events() -> None:
    events = [
        _event(1, delta="-0.5"),
        _event(1, session_id="sess-b", delta="-1.0"),
        _event(2, session_id="sess-b", round_number=2, delta="-1.0"),
    ]

    card = _scorecard(events, [1, 2])

    assert card.round(1).technique_red == Decimal("3.5")
    assert card.round(2).technique_red == Decimal("4.0")
    assert card.round(2).presentation_red == Decimal("6.0")
    assert card.total_events == 1
    assert card.last_sequence == 1


def test_scorecard_final_score_averages_technique_and_presentation_with_two_decimals() -> None:
    events = [
        # Round 1 red: 3.4 + 4.8 = 8.2; round 2 red: 3.8 + 5.7 = 9.5 -> 3.60 + 5.25 = 8.85 (not 8.9).
        _event(1, delta="-0.6"),
        _event(2, target=ScoreTarget.PRESENTATION_SPEED_POWER, delta="-1.2"),
        _event(3, round_number=2, delta="-0.2"),
        _event(4, round_number=2, target=ScoreTarget.PRESENTATION_RHYTHM_TEMPO, delta="-0.3"),
    ]

    card = _scorecard(events, [1, 2])

    assert card.final_score_red == Decimal("8.85")
    assert card.final_score_blue == Decimal("10.00")


def test_legacy_events_without_target_count_as_technique() -> None:
    assert parse_score_target(None) == ScoreTarget.TECHNIQUE
    assert parse_score_target("") == ScoreTarget.TECHNIQUE
    assert parse_score_target("presentation_speed_power") == ScoreTarget.PRESENTATION_SPEED_POWER
    with pytest.raises(ValidationError):
        parse_score_target("SOMETHING_ELSE")


def test_judge_aliases_follow_connection_order() -> None:
    assert judge_aliases(["sess-c", "sess-a", "sess-c", "sess-b"]) == {
        "sess-c": "J1",
        "sess-a": "J2",
        "sess-b": "J3",
    }
