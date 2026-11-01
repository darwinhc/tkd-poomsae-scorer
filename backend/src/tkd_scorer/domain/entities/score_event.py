from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tkd_scorer.domain.entities.common import AthleteSide, ScoreTarget


@dataclass
class ScoreEvent:
    id: str
    idempotency_key: str
    event_id: str
    session_id: str
    station_id: str
    match_id: str
    round_number: int
    athlete_side: AthleteSide
    score_delta: Decimal
    score_before: Decimal
    score_after: Decimal
    occurred_at: datetime
    sequence: int
    judge_name: str
    received_at: datetime
    processed_at: datetime
    # Legacy events without a target are technique deductions.
    score_target: ScoreTarget = ScoreTarget.TECHNIQUE


@dataclass
class IdempotencyRecord:
    id: str
    key: str
    operation: str
    response_payload: str
    created_at: datetime


@dataclass
class FinalizationRecord:
    id: str
    idempotency_key: str
    session_id: str
    station_id: str
    match_id: str
    checksum: str
    status: str
    reconciliation_notes: str
    created_at: datetime
    # Rounds the judge reported on finalize (the rounds of their scorecard).
    round_numbers: tuple[int, ...] = ()
    # JSON response returned to the judge, replayed when the same judge finalizes again.
    response_payload: str = ""
