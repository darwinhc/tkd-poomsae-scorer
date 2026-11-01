from datetime import UTC, timedelta

from tkd_scorer.application.dto.station_dto import ConnectStationInput, ConnectStationOutput
from tkd_scorer.application.mappers.station_mapper import to_station_view
from tkd_scorer.application.use_cases._datetime_format import to_iso_utc_z
from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import SessionStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.exceptions.errors import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort
from tkd_scorer.ports.realtime.realtime_port import RealtimePort
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort
from tkd_scorer.ports.repositories.station_repository_port import StationRepositoryPort
from tkd_scorer.ports.security.station_credential_service_port import StationCredentialServicePort
from tkd_scorer.ports.security.token_service_port import TokenServicePort


class ConnectStationUseCase:
    """Opens a judge session on a station (QR + PIN).

    A judge name has one active session per station. Reconnecting from the same device replaces the
    previous session silently; from another device it is a 409 unless the client asks to replace it
    (replace_existing_judge_session): the old session is then revoked and told so (session_revoked and
    judge_kicked with its sessionId). In both cases the new session continues the judge's scorecard
    (DeviceSession.scorecard_session_id), so the judge is counted once and its events keep counting.
    """

    def __init__(
        self,
        *,
        station_repository: StationRepositoryPort,
        session_repository: SessionRepositoryPort,
        audit_repository: AuditRepositoryPort,
        credential_service: StationCredentialServicePort,
        token_service: TokenServicePort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
        session_ttl_seconds: int,
        realtime: RealtimePort | None = None,
    ) -> None:
        self._realtime = realtime
        self._station_repository = station_repository
        self._session_repository = session_repository
        self._audit_repository = audit_repository
        self._credential_service = credential_service
        self._token_service = token_service
        self._clock = clock
        self._id_generator = id_generator
        self._session_ttl_seconds = session_ttl_seconds

    async def execute(self, request: ConnectStationInput) -> ConnectStationOutput:
        if not request.judge_name.strip():
            raise ValidationError("judgeName is required")
        resolved_judge_name = request.judge_name.strip()

        now = self._clock.now()
        station = self._station_repository.get_by_id(request.station_id)
        if station is None:
            raise NotFoundError("Station not found")
        if station.credential_expires_at:
            credential_expires_at = station.credential_expires_at
            if credential_expires_at.tzinfo is None:
                credential_expires_at = credential_expires_at.replace(tzinfo=UTC)
            if now.tzinfo is None:
                now = now.replace(tzinfo=UTC)
            if credential_expires_at < now:
                raise UnauthorizedError("Station credential expired")

        if not self._credential_service.verify(request.credential, station.credential_hash):
            raise UnauthorizedError("Invalid station credential")

        if station.expected_judge_name and station.expected_judge_name != resolved_judge_name:
            raise ConflictError("Judge does not match expected judge for station")

        active_sessions = self._session_repository.list_active_by_station(station.id)
        for active in active_sessions:
            if active.device_id == request.device_id and active.judge_name != resolved_judge_name:
                raise ConflictError("Device already connected with another judge identity")
            if (
                active.judge_name == resolved_judge_name
                and active.device_id != request.device_id
                and not request.replace_existing_judge_session
            ):
                raise ConflictError("Judge already connected with another active device")

        replaced: list[DeviceSession] = []
        for active in active_sessions:
            if active.judge_name == resolved_judge_name:
                self._session_repository.revoke(active.id)
                replaced.append(active)

        expires_at = now + timedelta(seconds=self._session_ttl_seconds)
        session_id = self._id_generator.new("sess")
        token = self._token_service.issue_access_token(
            session_id=session_id,
            station_id=station.id,
            judge_name=resolved_judge_name,
        )
        token_hash = self._token_service.hash_token(token)

        session = DeviceSession(
            id=session_id,
            station_id=station.id,
            judge_name=resolved_judge_name,
            device_id=request.device_id,
            token_hash=token_hash,
            status=SessionStatus.ACTIVE,
            created_at=now,
            expires_at=expires_at,
            scorecard_session_id=replaced[0].scorecard_key if replaced else None,
        )
        self._session_repository.save(session)

        station.mark_connected(session_id)
        self._station_repository.save(station)

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="station",
                action="connect",
                subject_id=station.id,
                actor=resolved_judge_name,
                details=f"device_id={request.device_id}",
                occurred_at=now,
            )
        )

        for previous in replaced:
            if previous.device_id == request.device_id:
                # Same device reconnecting: it already dropped the old session; telling it would sign it out.
                continue
            self._audit_repository.save(
                AuditEvent(
                    id=self._id_generator.new("audit"),
                    category="session",
                    action="replace",
                    subject_id=previous.id,
                    actor=resolved_judge_name,
                    details=f"new_session_id={session_id};device_id={request.device_id}",
                    occurred_at=now,
                )
            )
            await self._notify_replaced(previous, station_id=station.id, issued_at=now)

        return ConnectStationOutput(
            session_id=session.id,
            access_token=token,
            expires_at=expires_at,
            station=to_station_view(station),
        )

    async def _notify_replaced(self, previous: DeviceSession, *, station_id: str, issued_at) -> None:
        if self._realtime is None:
            return
        payload = {
            "sessionId": previous.id,
            "stationId": station_id,
            "reason": "replaced_by_new_device",
            "issuedAt": to_iso_utc_z(issued_at),
        }
        await self._realtime.publish_to_session(previous.id, "judge_kicked", payload)
        await self._realtime.publish_to_session(
            previous.id,
            "session_revoked",
            {"sessionId": previous.id, "reason": "replaced_by_new_device"},
        )
