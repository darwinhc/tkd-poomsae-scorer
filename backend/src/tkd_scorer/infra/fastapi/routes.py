import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Request

from tkd_scorer.application.dto.bootstrap_dto import GenerateBootstrapInput, ValidateBootstrapInput
from tkd_scorer.application.dto.match_dto import CreateMatchInput, FinalizeMatchInput
from tkd_scorer.application.dto.score_dto import IngestScoreEventInput
from tkd_scorer.application.dto.session_dto import RestoreSessionInput, RestoreSessionOutput
from tkd_scorer.application.dto.station_dto import ConnectStationInput
from tkd_scorer.application.use_cases._datetime_format import to_iso_utc_z
from tkd_scorer.domain.exceptions.errors import ForbiddenError, UnauthorizedError, ValidationError
from tkd_scorer.infra.fastapi.admin_auth import has_admin_login, is_admin_request
from tkd_scorer.infra.fastapi.dependencies import UseCases, get_use_cases
from tkd_scorer.infra.fastapi.schemas import (
    BootstrapGenerateRequest,
    BootstrapValidateRequest,
    ConnectStationRequest,
    CreateMatchRequest,
    FinalizeMatchRequest,
    MatchControlRequest,
    RestoreSessionRequest,
    ScoreEventRequest,
)

router = APIRouter()
score_logger = logging.getLogger("tkd_scorer.api.score_events")
finalize_logger = logging.getLogger("tkd_scorer.api.finalize")


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedError("Invalid Authorization header format")
    return parts[1].strip()


def _require_bearer_token(authorization: str | None) -> str:
    token = _extract_bearer_token(authorization)
    if not token:
        raise UnauthorizedError("Missing bearer token")
    return token


def _require_judge_session(
    use_cases: UseCases,
    authorization: str | None,
    *,
    allow_inactive: bool = False,
) -> RestoreSessionOutput:
    """The judge session of the Bearer token (same validation as /score-events)."""
    access_token = _require_bearer_token(authorization)
    return use_cases.restore_session.execute(
        RestoreSessionInput(access_token=access_token, allow_inactive=allow_inactive)
    )


def _require_admin(request: Request) -> None:
    if not is_admin_request(request):
        raise ForbiddenError("Administrator access required")


@dataclass(frozen=True)
class _MatchControlCaller:
    """Who calls a match-control endpoint: a judge (Bearer token) or the logged-in administrator."""

    judge: RestoreSessionOutput | None

    @property
    def station_id(self) -> str | None:
        return self.judge.station_id if self.judge is not None else None


def _match_control_caller(
    request: Request,
    use_cases: UseCases,
    authorization: str | None,
    *,
    allow_inactive: bool = False,
) -> _MatchControlCaller:
    if authorization or not has_admin_login(request):
        return _MatchControlCaller(
            judge=_require_judge_session(use_cases, authorization, allow_inactive=allow_inactive)
        )
    return _MatchControlCaller(judge=None)


def _reject_judge_reset(caller: _MatchControlCaller) -> None:
    # The match is shared: a judge must not delete the other judges' scores. A judge corrects its own
    # scorecard with compensating score events; deleting events is an administrator action.
    if caller.judge is not None:
        raise ForbiddenError("Judges cannot reset the shared match; only the administrator can")


@router.get("/health")
def health(
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict[str, str]:
    token = _extract_bearer_token(authorization)
    if token:
        use_cases.restore_session.execute(RestoreSessionInput(access_token=token))
    return {"status": "ok"}


@router.post("/bootstrap/generate")
def generate_bootstrap(
    raw_request: Request,
    request: BootstrapGenerateRequest,
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    _require_admin(raw_request)
    payload = use_cases.generate_bootstrap.execute(
        GenerateBootstrapInput(
            tournament_id=request.tournament_id,
            station_id=request.station_id,
            station_name=request.station_name,
        )
    )
    expires_at = to_iso_utc_z(payload.expires_at)
    return {
        "baseUrl": payload.base_url,
        "stationId": payload.station_id,
        "stationName": payload.station_name,
        "bootstrapToken": payload.bootstrap_token,
        "environment": payload.environment,
        "tournamentId": payload.tournament_id,
        "protocolVersion": payload.protocol_version,
        "expiresAt": expires_at,
        # Legacy compatibility fields:
        "base_url": payload.base_url,
        "station_id": payload.station_id,
        "station_name": payload.station_name,
        "bootstrap_token": payload.bootstrap_token,
        "tournament_id": payload.tournament_id,
        "protocol_version": payload.protocol_version,
        "expires_at": expires_at,
    }


@router.post("/bootstrap/validate")
def validate_bootstrap(
    raw_request: Request,
    request: BootstrapValidateRequest,
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    _require_admin(raw_request)
    claims = use_cases.validate_bootstrap.execute(
        ValidateBootstrapInput(bootstrap_token=request.bootstrap_token)
    )
    return {"valid": True, "claims": claims}


@router.get("/stations/active")
def list_active_stations(
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> list[dict]:
    bootstrap_token = _extract_bearer_token(authorization)
    if bootstrap_token:
        use_cases.validate_bootstrap.execute(ValidateBootstrapInput(bootstrap_token=bootstrap_token))

    stations = use_cases.list_active_stations.execute()
    return [{"id": item.id, "name": item.name, "status": item.status} for item in stations]


@router.post("/stations/connect")
async def connect_station(
    request: ConnectStationRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    bootstrap_token = _extract_bearer_token(authorization)
    if bootstrap_token:
        use_cases.validate_bootstrap.execute(ValidateBootstrapInput(bootstrap_token=bootstrap_token))

    result = await use_cases.connect_station.execute(
        ConnectStationInput(
            station_id=request.station_id,
            judge_name=request.judge_name,
            credential=request.credential,
            device_id=request.device_id,
            replace_existing_judge_session=request.replace_existing_judge_session,
        )
    )
    expires_at = to_iso_utc_z(result.expires_at) if result.expires_at else None
    return {
        "connected": True,
        "sessionId": result.session_id,
        "accessToken": result.access_token,
        "expiresAt": expires_at,
        "station": {
            "id": result.station.id,
            "name": result.station.name,
        },
        # Legacy compatibility fields:
        "session_id": result.session_id,
        "access_token": result.access_token,
        "expires_at": expires_at,
    }


@router.post("/sessions/restore")
def restore_session(
    request: RestoreSessionRequest,
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    result = use_cases.restore_session.execute(RestoreSessionInput(access_token=request.access_token))
    payload = asdict(result)
    payload["sessionId"] = result.session_id
    payload["stationId"] = result.station_id
    payload["judgeName"] = result.judge_name
    payload["expiresAt"] = to_iso_utc_z(result.expires_at) if result.expires_at else None
    return payload


@router.post("/matches")
def create_match(
    raw_request: Request,
    request: CreateMatchRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    restored = _require_judge_session(use_cases, authorization)
    if restored.session_id != request.session_id:
        raise UnauthorizedError("Session token mismatch")
    if restored.station_id != request.station_id:
        raise UnauthorizedError("Station token mismatch")
    if restored.judge_name != request.judge_name:
        raise UnauthorizedError("Judge token mismatch")
    default_starting_score = Decimal(str(raw_request.app.state.settings.create_match_default_starting_score))
    starting_score = request.starting_score if request.starting_score is not None else default_starting_score
    match = use_cases.create_match.execute(
        CreateMatchInput(
            station_id=request.station_id,
            session_id=request.session_id,
            judge_name=request.judge_name,
            competitor_left_name=request.competitor_left_name,
            competitor_right_name=request.competitor_right_name,
            total_rounds=request.total_rounds,
            starting_score=starting_score,
        )
    )
    return {
        "id": match.id,
        "stationId": match.station_id,
        "sessionId": match.session_id,
        "judgeName": match.judge_name,
        "status": match.status.value,
        "currentRound": match.current_round,
        "totalRounds": match.total_rounds,
    }


@router.post("/score-events")
async def ingest_score_event(
    request: ScoreEventRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    score_logger.info(
        "score_event_ingest_received station_id=%s session_id=%s judge_name=%s match_id=%s event_id=%s sequence=%s round=%s side=%s score_delta=%s",
        request.station_id,
        request.session_id,
        request.judge_name,
        request.match_id,
        request.event_id,
        request.sequence,
        request.round_number,
        request.athlete_side,
        request.score_delta,
    )
    try:
        access_token = _require_bearer_token(authorization)
        restored = use_cases.restore_session.execute(RestoreSessionInput(access_token=access_token))
        if restored.session_id != request.session_id:
            raise UnauthorizedError("Session token mismatch")
        if restored.station_id != request.station_id:
            raise UnauthorizedError("Station token mismatch")
        if restored.judge_name != request.judge_name:
            raise UnauthorizedError("Judge token mismatch")

        effective_idempotency_key = idempotency_key_header or request.idempotency_key
        if idempotency_key_header and request.idempotency_key and idempotency_key_header != request.idempotency_key:
            raise ValidationError("Idempotency key mismatch between header and body")

        result = await use_cases.ingest_score_event.execute(
            IngestScoreEventInput(
                event_id=request.event_id,
                idempotency_key=effective_idempotency_key,
                session_id=request.session_id,
                station_id=request.station_id,
                match_id=request.match_id,
                round_number=request.round_number,
                athlete_side=request.athlete_side.lower(),
                score_delta=request.score_delta,
                occurred_at=request.occurred_at,
                sequence=request.sequence,
                judge_name=request.judge_name,
                score_target=request.score_target,
            )
        )
        server_received_at = to_iso_utc_z(result.received_at)
        score_logger.info(
            "score_event_ingest_ok station_id=%s session_id=%s judge_name=%s event_id=%s sequence=%s idempotent_replay=%s",
            request.station_id,
            request.session_id,
            request.judge_name,
            result.event_id,
            result.sequence,
            result.idempotent_replay,
        )
        return {
            "acknowledged": True,
            "eventId": result.event_id,
            "serverReceivedAt": server_received_at,
            # Legacy compatibility fields:
            "event_id": result.event_id,
            "idempotentReplay": result.idempotent_replay,
            "idempotent_replay": result.idempotent_replay,
            "sequence": result.sequence,
            "score_before": str(result.score_before),
            "score_after": str(result.score_after),
            "received_at": server_received_at,
        }
    except Exception as exc:
        score_logger.warning(
            "score_event_ingest_failed station_id=%s session_id=%s judge_name=%s match_id=%s event_id=%s sequence=%s score_delta=%s error_type=%s error=%s",
            request.station_id,
            request.session_id,
            request.judge_name,
            request.match_id,
            request.event_id,
            request.sequence,
            request.score_delta,
            type(exc).__name__,
            str(exc),
        )
        raise


@router.post("/matches/finalize")
async def finalize_match(
    request: FinalizeMatchRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    try:
        access_token = _require_bearer_token(authorization)
        # A judge is released (session revoked) once its finalization reconciles; a retry of that same
        # finalization (lost response) must still get the original answer instead of a 401.
        restored = use_cases.restore_session.execute(
            RestoreSessionInput(access_token=access_token, allow_inactive=True)
        )
        if restored.session_id != request.session_id:
            raise UnauthorizedError("Session token mismatch")
        if restored.station_id != request.station_id:
            raise UnauthorizedError("Station token mismatch")
        if restored.judge_name != request.judge_name:
            raise UnauthorizedError("Judge token mismatch")

        fallback_idempotency_key = (
            f"finalize:{request.session_id}:{request.match_id}:{request.last_sequence}:{request.checksum}"
        )
        effective_idempotency_key = idempotency_key_header or request.idempotency_key or fallback_idempotency_key
        finalize_logger.info(
            (
                "finalize_match_received station_id=%s session_id=%s judge_name=%s "
                "match_id=%s total_events=%s last_sequence=%s"
            ),
            request.station_id,
            request.session_id,
            request.judge_name,
            request.match_id,
            request.total_events,
            request.last_sequence,
        )

        result = await use_cases.finalize_match.execute(
            FinalizeMatchInput(
                session_id=request.session_id,
                station_id=request.station_id,
                match_id=request.match_id,
                judge_name=request.judge_name,
                competitor_left_name=request.competitor_left_name,
                competitor_right_name=request.competitor_right_name,
                total_rounds=request.total_rounds,
                final_round=request.final_round,
                final_score_left=request.final_score_left,
                final_score_right=request.final_score_right,
                total_events=request.total_events,
                last_sequence=request.last_sequence,
                started_at=request.started_at,
                finished_at=request.finished_at,
                checksum=request.checksum,
                idempotency_key=effective_idempotency_key,
                rounds_summary=request.rounds_summary,
                session_active=restored.status == "active",
            )
        )
        finalize_logger.info(
            (
                "finalize_match_processed station_id=%s session_id=%s judge_name=%s "
                "requested_match_id=%s resolved_match_id=%s status=%s reconciled=%s checksum_mode=%s checksum_verified=%s"
            ),
            request.station_id,
            request.session_id,
            request.judge_name,
            request.match_id,
            result.match_id,
            result.status,
            result.reconciled,
            result.checksum_mode,
            result.checksum_verified,
        )
        server_received_at = to_iso_utc_z(datetime.now(UTC))
        return {
            "acknowledged": True,
            "eventId": effective_idempotency_key,
            "serverReceivedAt": server_received_at,
            # Useful reconciliation context. "status" is this judge's finalization; "matchStatus" is the shared
            # match, which only closes once every judge of the station has finalized.
            "status": result.status,
            "matchStatus": result.match_status,
            "judgesFinalized": result.judges_finalized,
            "judgesRequired": result.judges_required,
            "reconciled": result.reconciled,
            "notes": result.notes,
            "checksumVerified": result.checksum_verified,
            "checksumMode": result.checksum_mode,
            "reportedFinalScoreRed": (
                str(result.reported_final_score_left) if result.reported_final_score_left is not None else None
            ),
            "reportedFinalScoreBlue": (
                str(result.reported_final_score_right) if result.reported_final_score_right is not None else None
            ),
            "serverFinalScoreRed": str(result.server_final_score_left) if result.server_final_score_left is not None else None,
            "serverFinalScoreBlue": (
                str(result.server_final_score_right) if result.server_final_score_right is not None else None
            ),
            # Legacy compatibility fields:
            "match_id": result.match_id,
            "idempotent_replay": result.idempotent_replay,
            "checksum_verified": result.checksum_verified,
            "checksum_mode": result.checksum_mode,
        }
    except Exception as exc:
        finalize_logger.warning(
            (
                "finalize_match_failed station_id=%s session_id=%s judge_name=%s "
                "match_id=%s total_events=%s last_sequence=%s error_type=%s error=%s"
            ),
            request.station_id,
            request.session_id,
            request.judge_name,
            request.match_id,
            request.total_events,
            request.last_sequence,
            type(exc).__name__,
            str(exc),
        )
        raise


@router.post("/matches/{match_id}/next-round")
async def next_round(
    match_id: str,
    raw_request: Request,
    request: MatchControlRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    caller = _match_control_caller(raw_request, use_cases, authorization)
    result = await use_cases.next_round.execute(match_id, request.actor, station_id=caller.station_id)
    return asdict(result)


@router.post("/matches/{match_id}/reset-round")
async def reset_round(
    match_id: str,
    raw_request: Request,
    request: MatchControlRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    _reject_judge_reset(_match_control_caller(raw_request, use_cases, authorization))
    result = await use_cases.reset_round.execute(match_id, request.actor)
    return asdict(result)


@router.post("/matches/{match_id}/reset-match")
async def reset_match(
    match_id: str,
    raw_request: Request,
    request: MatchControlRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    _reject_judge_reset(_match_control_caller(raw_request, use_cases, authorization))
    result = await use_cases.reset_match.execute(match_id, request.actor)
    return asdict(result)


@router.get("/matches/{match_id}/summary")
def match_summary(
    match_id: str,
    raw_request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    # A judge released after finalizing may still read the summary of its match.
    caller = _match_control_caller(raw_request, use_cases, authorization, allow_inactive=True)
    result = use_cases.match_summary.execute(match_id, station_id=caller.station_id)
    return asdict(result)


@router.get("/stations/{station_id}/active-session")
def station_active_session(
    station_id: str,
    raw_request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    caller = _match_control_caller(raw_request, use_cases, authorization)
    if caller.station_id is not None and caller.station_id != station_id:
        raise UnauthorizedError("Station token mismatch")
    result = use_cases.station_active_session.execute(station_id)
    return asdict(result)


@router.get("/stations/{station_id}/active-match-state")
def station_active_match_state(
    station_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
    use_cases: UseCases = Depends(get_use_cases),
) -> dict:
    access_token = _require_bearer_token(authorization)
    restored = use_cases.restore_session.execute(RestoreSessionInput(access_token=access_token))
    result = use_cases.station_active_match_state.execute(station_id)
    if restored.station_id != station_id:
        raise UnauthorizedError("Station token mismatch")

    updated_at = to_iso_utc_z(result.updated_at)
    return {
        "hasActiveMatch": result.has_active_match,
        "matchId": result.match_id,
        "competitorRedName": result.competitor_red_name,
        "competitorBlueName": result.competitor_blue_name,
        "updatedAt": updated_at,
        # Legacy compatibility fields:
        "has_active_match": result.has_active_match,
        "match_id": result.match_id,
        "competitor_red_name": result.competitor_red_name,
        "competitor_blue_name": result.competitor_blue_name,
        "updated_at": updated_at,
    }
