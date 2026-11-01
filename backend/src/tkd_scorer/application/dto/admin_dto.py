from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class AdminStationRow:
    station_id: str
    station_name: str
    status: str
    active_session_id: str | None
    judge_name: str | None
    device_id: str | None
    active_sessions_count: int = 0
    judge_names: list[str] = field(default_factory=list)
    active_session_ids: list[str] = field(default_factory=list)
    connected_sessions_count: int = 0
    connected_judge_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AdminDashboardView:
    generated_at: datetime
    total_stations: int
    occupied_stations: int
    active_sessions: int
    active_matches: int
    recent_matches: int
    stations: list[AdminStationRow]


@dataclass(frozen=True)
class AdminSessionView:
    session_id: str
    judge_name: str
    device_id: str
    status: str
    expires_at: datetime | None
    is_connected: bool = False


@dataclass(frozen=True)
class AdminCompetitorRoundResultView:
    round_number: int
    tec_score: Decimal
    pres_score: Decimal
    score: Decimal


@dataclass(frozen=True)
class AdminCompetitorResultView:
    side: str
    competitor_name: str
    # Consolidated poomsae (round) scores of rounds 1 and 2, None when the round has no data.
    poomsae_1: Decimal | None
    poomsae_2: Decimal | None
    # Averages over the rounds of the consolidated technique and presentation.
    tec_score: Decimal | None
    pres_score: Decimal | None
    # Match score: mean of the consolidated round scores.
    final_score: Decimal | None
    rounds: list[AdminCompetitorRoundResultView] = field(default_factory=list)


@dataclass(frozen=True)
class AdminMatchResultView:
    match_id: str
    station_id: str
    judge_name: str
    status: str
    current_round: int
    total_rounds: int
    competitor_results: list[AdminCompetitorResultView]
    finalization_notes_key: str | None = None
    judge_names: list[str] = field(default_factory=list)
    judges_finalized: int = 0
    judges_required: int = 1
    winner_side: str | None = None


@dataclass(frozen=True)
class AdminStationDetailView:
    station_id: str
    station_name: str
    status: str
    active_session: AdminSessionView | None
    active_sessions: list[AdminSessionView]
    credential_masked: str
    credential_revealed: str | None
    credential_expires_at: datetime | None
    bootstrap_payload_json: str
    current_match: AdminMatchResultView | None


@dataclass(frozen=True)
class AdminResultsView:
    generated_at: datetime
    results: list[AdminMatchResultView]


@dataclass(frozen=True)
class AdminHistoryView:
    generated_at: datetime
    matches: list[AdminMatchResultView]


@dataclass(frozen=True)
class StationCredentialView:
    station_id: str
    masked: str
    revealed: str | None
    expires_at: datetime | None
    # The stored PIN cannot be decrypted (the server key changed): the operator must rotate it.
    unreadable: bool = False


@dataclass(frozen=True)
class AdminStationLiveSnapshot:
    station_id: str
    station_name: str
    credential_masked: str
    credential_revealed: str | None
    credential_expires_at: datetime | None
    bootstrap_payload_json: str
    credential_unreadable: bool = False


@dataclass(frozen=True)
class AdminJudgeSubmissionView:
    judge_name: str
    match_id: str
    status: str
    red_score: Decimal
    blue_score: Decimal
    finalized_at: datetime | None
    alias: str = ""
    reconciled: bool = False
    session_id: str = ""


@dataclass(frozen=True)
class AdminConsolidatedResultView:
    judges_required: int
    judges_finalized: int
    all_finalized: bool
    red_score: Decimal | None
    blue_score: Decimal | None
    winner_side: str | None
    winner_label_key: str | None


@dataclass(frozen=True)
class AdminJudgeFinalizationStatusView:
    judge_name: str
    finalized: bool
    alias: str = ""
    connected: bool = False
    reconciled: bool = False
    # Removed by the operator before finalizing: not counted nor consolidated.
    removed: bool = False


@dataclass(frozen=True)
class AdminJudgeDeltaEventView:
    judge_name: str
    sequence: int
    round_number: int
    athlete_side: str
    score_delta: Decimal
    occurred_at: datetime
    alias: str = ""
    score_target: str = "TECHNIQUE"
    score_after: Decimal | None = None


@dataclass(frozen=True)
class AdminRoundConsolidatedView:
    round_number: int
    red_score: Decimal | None
    blue_score: Decimal | None


@dataclass(frozen=True)
class AdminScoreboardJudgeColumnView:
    alias: str
    session_id: str
    judge_name: str
    connected: bool
    finalized: bool
    reconciled: bool
    removed: bool = False


@dataclass(frozen=True)
class AdminScoreboardRowView:
    # One value per judge column (same order as the columns); None when the judge has no data for the round.
    judge_values: list[Decimal | None]
    consolidated: Decimal | None


@dataclass(frozen=True)
class AdminScoreboardRoundView:
    round_number: int
    poomsae: str | None
    technique: AdminScoreboardRowView
    presentation: AdminScoreboardRowView
    round_score: Decimal | None


@dataclass(frozen=True)
class AdminScoreboardSideView:
    side: str
    competitor_name: str | None
    rounds: list[AdminScoreboardRoundView]
    total: Decimal | None


@dataclass(frozen=True)
class AdminCategoryOptionView:
    category_id: str
    category_label: str
    poomsaes: list[str]


@dataclass(frozen=True)
class AdminMatchStartView:
    categories: list[AdminCategoryOptionView]


@dataclass(frozen=True)
class AdminStartMatchResult:
    match_id: str
    station_id: str
    category_id: str
    category_label: str
    drawn_poomsaes: list[str]


@dataclass(frozen=True)
class AdminDrawPoomsaesView:
    category_id: str
    category_label: str
    total_rounds: int
    drawn_poomsaes: list[str]


@dataclass(frozen=True)
class AdminActiveMatchView:
    station_id: str
    match_id: str
    competitor_left_name: str
    competitor_right_name: str
    current_round: int
    total_rounds: int
    category_label: str | None
    drawn_poomsaes: list[str]
    timer_status: str
    elapsed_seconds: int
    elapsed_label: str
    timer_reference_started_at: str | None
    primary_action: str
    primary_label_key: str
    can_pause_timer: bool
    can_reset_round: bool
    can_finalize_match: bool


@dataclass(frozen=True)
class AdminStationScoreboardView:
    station_id: str
    station_name: str
    generated_at: datetime
    judges_required: int
    connected_judges_count: int
    connected_judges: list[AdminSessionView]
    scoring_mode_valid: bool
    scoring_mode_label_key: str
    has_active_match: bool
    match_category_id: str | None
    match_category_label: str | None
    match_poomsaes: list[str]
    competitor_left_name: str | None
    competitor_right_name: str | None
    current_red_score: Decimal | None
    current_blue_score: Decimal | None
    current_match_status: str | None
    current_round: int | None
    total_rounds: int | None
    judge_submissions: list[AdminJudgeSubmissionView]
    judge_finalization: list[AdminJudgeFinalizationStatusView]
    round_consolidated: list[AdminRoundConsolidatedView]
    consolidated: AdminConsolidatedResultView
    start_view: AdminMatchStartView
    pending_competitor_left_name: str | None = None
    pending_competitor_right_name: str | None = None
    judge_delta_events: list[AdminJudgeDeltaEventView] = field(default_factory=list)
    current_match_id: str | None = None
    judge_columns: list[AdminScoreboardJudgeColumnView] = field(default_factory=list)
    side_scorecards: list[AdminScoreboardSideView] = field(default_factory=list)
    # True when the scoreboard shows the last closed match of the station (result screen).
    showing_closed_match: bool = False
