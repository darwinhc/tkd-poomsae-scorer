import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tkd_scorer.adapters.repositories.sqlalchemy_repositories import (
    SqlAlchemyAuditRepository,
    SqlAlchemyMatchRepository,
    SqlAlchemySessionRepository,
)
from tkd_scorer.adapters.security.system_clock_and_ids import UtcClock, UuidIdGenerator
from tkd_scorer.adapters.security.system_services import JwtTokenService
from tkd_scorer.application.dto.realtime_dto import (
    JudgeMatchCompletedSignalInput,
    JudgeRoundCompletedSignalInput,
)
from tkd_scorer.application.use_cases.handle_judge_ws_signals_use_case import (
    HandleJudgeWsSignalsUseCase,
)
from tkd_scorer.domain.entities.common import MatchStatus, SessionStatus
from tkd_scorer.domain.exceptions.errors import NotFoundError, UnauthorizedError, ValidationError

router = APIRouter()
logger = logging.getLogger("tkd_scorer.api.websocket")


def _extract_query_value(websocket: WebSocket, camel: str, snake: str) -> str | None:
    return websocket.query_params.get(camel) or websocket.query_params.get(snake)


def _send_event_payload(event_type: str, payload: dict) -> dict:
    return {
        "type": event_type,
        "eventType": event_type,
        "payload": payload,
    }


def _to_iso_utc_z(value: datetime) -> str:
    normalized = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _judge_settings_payload(websocket: WebSocket) -> dict:
    settings = websocket.app.state.settings
    return {
        "defaultRounds": max(1, int(settings.judge_default_rounds)),
        "defaultStartingScore": float(settings.judge_default_starting_score),
        "presentationCategoryStartScore": float(settings.judge_presentation_category_start_score),
        "actionValue1": float(settings.judge_action_value_1),
        "actionValue2": float(settings.judge_action_value_2),
        "issuedAt": _to_iso_utc_z(datetime.now(UTC)),
    }


def _active_match_state_payload(websocket: WebSocket, *, station_id: str) -> dict:
    db = websocket.app.state.session_factory()
    try:
        matches = SqlAlchemyMatchRepository(db)
        sessions = SqlAlchemySessionRepository(db)
        lookup_limit = max(1, int(websocket.app.state.settings.match_query_limit_active_lookup))
        active = matches.list_recent(
            limit=lookup_limit,
            statuses=[MatchStatus.IN_PROGRESS.value, MatchStatus.FINALIZATION_PENDING.value],
        )
        active_sessions = sessions.list_active_by_station(station_id)
        for match in active:
            if match.station_id != station_id or not match.is_live(active_sessions):
                continue
            return {
                "hasActiveMatch": True,
                "matchId": match.id,
                "competitorRedName": match.competitor_left_name,
                "competitorBlueName": match.competitor_right_name,
                "issuedAt": _to_iso_utc_z(datetime.now(UTC)),
            }
        return {
            "hasActiveMatch": False,
            "matchId": None,
            "competitorRedName": None,
            "competitorBlueName": None,
            "issuedAt": _to_iso_utc_z(datetime.now(UTC)),
        }
    finally:
        db.close()


async def _send_contract_initial_events(websocket: WebSocket, *, station_id: str) -> None:
    await websocket.send_json(
        _send_event_payload(
            "judge_settings_updated",
            _judge_settings_payload(websocket),
        )
    )
    await websocket.send_json(
        _send_event_payload(
            "active_match_state",
            _active_match_state_payload(websocket, station_id=station_id),
        )
    )


def _message_payload(message: dict) -> dict:
    payload = message.get("payload")
    return payload if isinstance(payload, dict) else message


def _extract_value(message: dict, camel: str, snake: str) -> str | None:
    payload = _message_payload(message)
    value = payload.get(camel) if isinstance(payload, dict) else None
    if value is None:
        value = payload.get(snake) if isinstance(payload, dict) else None
    if value is None:
        value = message.get(camel) or message.get(snake)
    return str(value).strip() if isinstance(value, str) else value


def _parse_positive_int(raw: object, *, field_name: str) -> int:
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be an integer") from exc
    if parsed <= 0:
        raise ValidationError(f"{field_name} must be greater than zero")
    return parsed


def _parse_optional_datetime(raw: object, *, field_name: str) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str):
        raise ValidationError(f"{field_name} must be an ISO datetime string")

    value = raw.strip()
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be a valid ISO datetime") from exc
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _build_ws_signals_use_case(websocket: WebSocket, db) -> HandleJudgeWsSignalsUseCase:
    return HandleJudgeWsSignalsUseCase(
        session_repository=SqlAlchemySessionRepository(db),
        match_repository=SqlAlchemyMatchRepository(db),
        audit_repository=SqlAlchemyAuditRepository(db),
        realtime=websocket.app.state.realtime,
        clock=UtcClock(),
        id_generator=UuidIdGenerator(),
    )


async def _handle_judge_round_completed(websocket: WebSocket, message: dict) -> dict:
    match_id = _extract_value(message, "matchId", "match_id")
    session_id = _extract_value(message, "sessionId", "session_id")
    station_id = _extract_value(message, "stationId", "station_id")
    judge_name = _extract_value(message, "judgeName", "judge_name")
    if not match_id:
        raise ValidationError("matchId is required")
    if not session_id:
        raise ValidationError("sessionId is required")
    if not station_id:
        raise ValidationError("stationId is required")
    if not judge_name:
        raise ValidationError("judgeName is required")

    round_number = _parse_positive_int(
        _extract_value(message, "roundNumber", "round_number"),
        field_name="roundNumber",
    )
    finished_at = _parse_optional_datetime(
        _extract_value(message, "finishedAt", "finished_at"),
        field_name="finishedAt",
    )
    device_id = _extract_value(message, "deviceId", "device_id")

    db = websocket.app.state.session_factory()
    try:
        use_case = _build_ws_signals_use_case(websocket, db)
        output = await use_case.handle_round_completed(
            JudgeRoundCompletedSignalInput(
                match_id=match_id,
                round_number=round_number,
                session_id=session_id,
                station_id=station_id,
                judge_name=judge_name,
                device_id=device_id,
                finished_at=finished_at,
            )
        )
        db.commit()
        return {
            "message": "judge_round_completed_received",
            "matchId": output.match_id,
            "sessionId": output.session_id,
            "stationId": output.station_id,
            "judgeName": output.judge_name,
            "acceptedAt": _to_iso_utc_z(output.accepted_at),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _handle_judge_match_completed(websocket: WebSocket, message: dict) -> dict:
    match_id = _extract_value(message, "matchId", "match_id")
    session_id = _extract_value(message, "sessionId", "session_id")
    station_id = _extract_value(message, "stationId", "station_id")
    judge_name = _extract_value(message, "judgeName", "judge_name")
    checksum = _extract_value(message, "checksum", "checksum")
    if not match_id:
        raise ValidationError("matchId is required")
    if not session_id:
        raise ValidationError("sessionId is required")
    if not station_id:
        raise ValidationError("stationId is required")
    if not judge_name:
        raise ValidationError("judgeName is required")
    if not checksum:
        raise ValidationError("checksum is required")

    final_round = _parse_positive_int(
        _extract_value(message, "finalRound", "final_round"),
        field_name="finalRound",
    )
    finished_at = _parse_optional_datetime(
        _extract_value(message, "finishedAt", "finished_at"),
        field_name="finishedAt",
    )
    device_id = _extract_value(message, "deviceId", "device_id")

    db = websocket.app.state.session_factory()
    try:
        use_case = _build_ws_signals_use_case(websocket, db)
        output = await use_case.handle_match_completed(
            JudgeMatchCompletedSignalInput(
                match_id=match_id,
                final_round=final_round,
                checksum=checksum,
                session_id=session_id,
                station_id=station_id,
                judge_name=judge_name,
                device_id=device_id,
                finished_at=finished_at,
            )
        )
        db.commit()
        return {
            "message": "judge_match_completed_received",
            "matchId": output.match_id,
            "sessionId": output.session_id,
            "stationId": output.station_id,
            "judgeName": output.judge_name,
            "acceptedAt": _to_iso_utc_z(output.accepted_at),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _cleanup_disconnected_session(websocket: WebSocket, binding) -> None:
    session_id = binding.session_id
    station_id = binding.station_id
    if not session_id or not station_id:
        return

    logger.info(
        "ws_disconnect_connection_removed station_id=%s session_id=%s",
        station_id,
        session_id,
    )
    await websocket.app.state.realtime.publish_to_station(
        station_id,
        "station_disconnected",
        {
            "stationId": station_id,
            "sessionId": session_id,
            "reason": "websocket_disconnected",
            "issuedAt": _to_iso_utc_z(datetime.now(UTC)),
        },
    )
    await websocket.app.state.realtime.publish_to_station(
        station_id,
        "active_match_state",
        _active_match_state_payload(websocket, station_id=station_id),
    )


def _require_bound_judge(websocket: WebSocket, connection_id: str, message: dict) -> None:
    """Judge signals are accepted only for the session and station this connection authenticated as."""
    binding = websocket.app.state.connection_hub.binding_for(connection_id)
    if binding is None or not binding.session_id:
        raise UnauthorizedError("WebSocket connection is not bound to a judge session")
    if _extract_value(message, "sessionId", "session_id") != binding.session_id:
        raise UnauthorizedError("WebSocket signal session mismatch")
    if _extract_value(message, "stationId", "station_id") != binding.station_id:
        raise UnauthorizedError("WebSocket signal station mismatch")


def _validate_ws_token(websocket: WebSocket, *, session_id: str, station_id: str, token: str) -> None:
    settings = websocket.app.state.settings
    token_service = JwtTokenService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        token_ttl_seconds=settings.operational_token_ttl_seconds,
    )
    claims = token_service.parse_access_token(token)
    if claims.get("session_id") != session_id:
        raise UnauthorizedError("WebSocket token session mismatch")
    if claims.get("station_id") != station_id:
        raise UnauthorizedError("WebSocket token station mismatch")

    db = websocket.app.state.session_factory()
    try:
        sessions = SqlAlchemySessionRepository(db)
        session = sessions.get_by_id(session_id)
        if session is None:
            raise UnauthorizedError("WebSocket session not found")
        if session.status != SessionStatus.ACTIVE:
            raise UnauthorizedError("WebSocket session is not active")
        if session.station_id != station_id:
            raise UnauthorizedError("WebSocket session/station mismatch")

        by_hash = sessions.get_by_token_hash(token_service.hash_token(token))
        if by_hash is None or by_hash.id != session_id:
            raise UnauthorizedError("WebSocket access token does not match active session")
    finally:
        db.close()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    hub = websocket.app.state.connection_hub
    connection_id = f"ws-{uuid.uuid4()}"
    await hub.register(connection_id, websocket)
    settings = websocket.app.state.settings
    ping_interval_seconds = max(1, int(settings.websocket_ping_interval_seconds))
    stale_timeout_seconds = max(ping_interval_seconds + 1, int(settings.websocket_stale_timeout_seconds))
    last_seen_at = datetime.now(UTC)

    session_id_qs = _extract_query_value(websocket, "sessionId", "session_id")
    station_id_qs = _extract_query_value(websocket, "stationId", "station_id")
    token_qs = websocket.query_params.get("token")

    try:
        if session_id_qs and station_id_qs and token_qs:
            _validate_ws_token(
                websocket,
                session_id=session_id_qs,
                station_id=station_id_qs,
                token=token_qs,
            )
            await hub.bind(
                connection_id,
                session_id=session_id_qs,
                station_id=station_id_qs,
                device_id=websocket.query_params.get("deviceId"),
            )
            await websocket.send_json(
                _send_event_payload(
                    "server_notice",
                    {
                        "connectionId": connection_id,
                        "message": "connected",
                        "sessionId": session_id_qs,
                        "stationId": station_id_qs,
                    },
                )
            )
            await _send_contract_initial_events(websocket, station_id=station_id_qs)
        else:
            await websocket.send_json(
                _send_event_payload(
                    "server_notice",
                    {
                        "connectionId": connection_id,
                        "message": "connected",
                    },
                )
            )

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=ping_interval_seconds)
                last_seen_at = datetime.now(UTC)
            except asyncio.TimeoutError:
                now = datetime.now(UTC)
                idle_seconds = (now - last_seen_at).total_seconds()
                if idle_seconds >= stale_timeout_seconds:
                    logger.info(
                        "ws_connection_stale_timeout connection_id=%s idle_seconds=%s stale_timeout_seconds=%s",
                        connection_id,
                        int(idle_seconds),
                        stale_timeout_seconds,
                    )
                    binding = await hub.unregister(connection_id)
                    if binding is not None:
                        await _cleanup_disconnected_session(websocket, binding)
                    await websocket.close(code=1001)
                    return

                # Keep-alive: the peer answers with "pong".
                await websocket.send_json(_send_event_payload("ping", {"message": "ping"}))
                continue
            message_type = message.get("type")

            if message_type == "bind":
                session_id = message.get("sessionId") or message.get("session_id")
                station_id = message.get("stationId") or message.get("station_id")
                if not session_id or not station_id:
                    await websocket.send_json(
                        _send_event_payload(
                            "server_notice",
                            {"message": "bind requires sessionId and stationId"},
                        )
                    )
                    continue
                # The token is always required and checked against the session and station (close 1008).
                token = _extract_value(message, "token", "accessToken") or _extract_value(
                    message, "access_token", "access_token"
                )
                if not token:
                    raise UnauthorizedError("bind requires the session access token")
                _validate_ws_token(websocket, session_id=session_id, station_id=station_id, token=token)
                await hub.bind(
                    connection_id,
                    session_id=session_id,
                    station_id=station_id,
                    device_id=message.get("deviceId") or message.get("device_id"),
                )
                await websocket.send_json(
                    _send_event_payload(
                        "server_notice",
                        {
                            "message": "bound",
                            "sessionId": session_id,
                            "stationId": station_id,
                        },
                    )
                )
                await _send_contract_initial_events(websocket, station_id=station_id)
            elif message_type == "ping":
                # Answered once with "pong"; an older peer that answers our "ping" with "ping" gets one reply
                # and the exchange stops there.
                await websocket.send_json(_send_event_payload("pong", {"message": "pong"}))
            elif message_type == "pong":
                # Keep-alive answer: receiving it already refreshed last_seen_at; never answered.
                continue
            elif message_type == "judge_round_completed":
                _require_bound_judge(websocket, connection_id, message)
                try:
                    notice = await _handle_judge_round_completed(websocket, message)
                    await websocket.send_json(_send_event_payload("server_notice", notice))
                except UnauthorizedError:
                    raise
                except (ValidationError, NotFoundError) as exc:
                    logger.warning(
                        "ws_judge_round_completed_failed error_type=%s error=%s payload=%s",
                        type(exc).__name__,
                        str(exc),
                        message,
                    )
                    await websocket.send_json(
                        _send_event_payload(
                            "server_notice",
                            {
                                "message": "judge_round_completed_failed",
                                "error": str(exc),
                            },
                        )
                    )
            elif message_type == "judge_match_completed":
                _require_bound_judge(websocket, connection_id, message)
                try:
                    notice = await _handle_judge_match_completed(websocket, message)
                    await websocket.send_json(_send_event_payload("server_notice", notice))
                except UnauthorizedError:
                    raise
                except (ValidationError, NotFoundError) as exc:
                    logger.warning(
                        "ws_judge_match_completed_failed error_type=%s error=%s payload=%s",
                        type(exc).__name__,
                        str(exc),
                        message,
                    )
                    await websocket.send_json(
                        _send_event_payload(
                            "server_notice",
                            {
                                "message": "judge_match_completed_failed",
                                "error": str(exc),
                            },
                        )
                    )
            else:
                await websocket.send_json(
                    _send_event_payload(
                        "server_notice",
                        {"message": "unknown message type"},
                    )
                )
    except WebSocketDisconnect:
        binding = await hub.unregister(connection_id)
        if binding is not None:
            await _cleanup_disconnected_session(websocket, binding)
    except UnauthorizedError:
        logger.warning("ws_connection_unauthorized connection_id=%s", connection_id)
        await hub.unregister(connection_id)
        await websocket.close(code=1008)
