from datetime import datetime, timezone
from decimal import Decimal

from tkd_scorer.domain.entities.common import AthleteSide
from tkd_scorer.domain.entities.score_event import ScoreEvent
from tkd_scorer.domain.services.scoring import compute_score


def test_compute_score_uses_deterministic_sequence_order() -> None:
    base_time = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
    events = [
        ScoreEvent(
            id="1",
            idempotency_key="a",
            event_id="e1",
            session_id="s",
            station_id="st",
            match_id="m",
            round_number=1,
            athlete_side=AthleteSide.RED,
            score_delta=Decimal("-0.3"),
            score_before=Decimal("10.0"),
            score_after=Decimal("9.7"),
            occurred_at=base_time,
            sequence=2,
            judge_name="Judge 1",
            received_at=base_time,
            processed_at=base_time,
        ),
        ScoreEvent(
            id="2",
            idempotency_key="b",
            event_id="e2",
            session_id="s",
            station_id="st",
            match_id="m",
            round_number=1,
            athlete_side=AthleteSide.RED,
            score_delta=Decimal("+0.1"),
            score_before=Decimal("9.7"),
            score_after=Decimal("9.8"),
            occurred_at=base_time,
            sequence=1,
            judge_name="Judge 1",
            received_at=base_time,
            processed_at=base_time,
        ),
    ]

    result = compute_score(Decimal("10.0"), events)

    assert result == Decimal("9.8")
