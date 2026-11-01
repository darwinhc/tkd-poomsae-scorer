from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ContractBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class BootstrapGenerateRequest(ContractBaseModel):
    station_id: str = Field(alias="stationId")
    station_name: str = Field(alias="stationName")
    tournament_id: str = Field(alias="tournamentId")


class BootstrapValidateRequest(ContractBaseModel):
    bootstrap_token: str = Field(alias="bootstrapToken")


class ConnectStationRequest(ContractBaseModel):
    station_id: str = Field(alias="stationId")
    judge_name: str = Field(alias="judgeName")
    credential: str
    device_id: str = Field(alias="deviceId")
    replace_existing_judge_session: bool = Field(
        default=False,
        validation_alias=AliasChoices("replaceExistingJudgeSession", "replace_existing_judge_session"),
    )


class RestoreSessionRequest(ContractBaseModel):
    access_token: str = Field(alias="accessToken")


class CreateMatchRequest(ContractBaseModel):
    station_id: str = Field(alias="stationId")
    session_id: str = Field(alias="sessionId")
    judge_name: str = Field(alias="judgeName")
    competitor_left_name: str = Field(alias="competitorLeftName")
    competitor_right_name: str = Field(alias="competitorRightName")
    total_rounds: int = Field(default=2, alias="totalRounds")
    starting_score: Decimal | None = Field(default=None, alias="startingScore")


class ScoreEventRequest(ContractBaseModel):
    event_id: str = Field(alias="eventId")
    idempotency_key: str = Field(alias="idempotencyKey")
    session_id: str = Field(alias="sessionId")
    station_id: str = Field(alias="stationId")
    device_id: str | None = Field(default=None, alias="deviceId")
    match_id: str = Field(alias="matchId")
    round_number: int = Field(alias="roundNumber")
    athlete_side: str = Field(alias="athleteSide")
    score_target: str | None = Field(default=None, alias="scoreTarget")
    score_delta: Decimal = Field(alias="scoreDelta")
    score_before: Decimal | None = Field(default=None, alias="scoreBefore")
    score_after: Decimal | None = Field(default=None, alias="scoreAfter")
    occurred_at: datetime = Field(alias="occurredAt")
    sequence: int
    judge_name: str = Field(alias="judgeName")


class FinalizeMatchRequest(ContractBaseModel):
    session_id: str = Field(alias="sessionId")
    station_id: str = Field(alias="stationId")
    match_id: str = Field(alias="matchId")
    judge_name: str = Field(alias="judgeName")
    competitor_left_name: str = Field(alias="competitorLeftName")
    competitor_right_name: str = Field(alias="competitorRightName")
    total_rounds: int = Field(alias="totalRounds")
    final_round: int = Field(alias="finalRound")
    final_score_left: Decimal = Field(
        validation_alias=AliasChoices("finalScoreLeft", "finalScoreRed", "final_score_left")
    )
    final_score_right: Decimal = Field(
        validation_alias=AliasChoices("finalScoreRight", "finalScoreBlue", "final_score_right")
    )
    total_events: int = Field(alias="totalEvents")
    last_sequence: int = Field(validation_alias=AliasChoices("lastSequence", "finalSequence", "last_sequence"))
    started_at: datetime = Field(alias="startedAt")
    finished_at: datetime = Field(alias="finishedAt")
    checksum: str
    rounds_summary: list[dict] | None = Field(default=None, alias="roundsSummary")
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class MatchControlRequest(ContractBaseModel):
    actor: str


class WebSocketBindMessage(ContractBaseModel):
    type: str
    connection_id: str | None = Field(default=None, alias="connectionId")
    session_id: str = Field(alias="sessionId")
    station_id: str = Field(alias="stationId")
    device_id: str | None = Field(default=None, alias="deviceId")
