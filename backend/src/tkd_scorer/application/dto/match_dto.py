from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class CreateMatchInput:
    station_id: str
    session_id: str
    judge_name: str
    competitor_left_name: str
    competitor_right_name: str
    total_rounds: int = 2
    starting_score: Decimal = Decimal("4.0")


@dataclass(frozen=True)
class MatchSummaryOutput:
    match_id: str
    station_id: str
    judge_name: str
    status: str
    current_round: int
    total_rounds: int
    red_score: Decimal | None
    blue_score: Decimal | None
    total_events: int


@dataclass(frozen=True)
class FinalizeMatchInput:
    session_id: str
    station_id: str
    match_id: str
    judge_name: str
    competitor_left_name: str
    competitor_right_name: str
    total_rounds: int
    final_round: int
    final_score_left: Decimal
    final_score_right: Decimal
    total_events: int
    last_sequence: int
    started_at: datetime
    finished_at: datetime
    checksum: str
    idempotency_key: str
    rounds_summary: list[dict] | None = None
    # False when the judge session was already released (it can only replay its own finalization).
    session_active: bool = True


@dataclass(frozen=True)
class FinalizeMatchOutput:
    match_id: str
    status: str
    reconciled: bool
    notes: str
    idempotent_replay: bool
    checksum_verified: bool = False
    checksum_mode: str = "mismatch"
    reported_final_score_left: Decimal | None = None
    reported_final_score_right: Decimal | None = None
    server_final_score_left: Decimal | None = None
    server_final_score_right: Decimal | None = None
    match_status: str | None = None
    judges_finalized: int = 0
    judges_required: int = 1
