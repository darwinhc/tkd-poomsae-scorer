from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class IngestScoreEventInput:
    event_id: str
    idempotency_key: str
    session_id: str
    station_id: str
    match_id: str
    round_number: int
    athlete_side: str
    score_delta: Decimal
    occurred_at: datetime
    sequence: int
    judge_name: str
    score_target: str | None = None


@dataclass(frozen=True)
class IngestScoreEventOutput:
    event_id: str
    idempotent_replay: bool
    sequence: int
    score_before: Decimal
    score_after: Decimal
    received_at: datetime
