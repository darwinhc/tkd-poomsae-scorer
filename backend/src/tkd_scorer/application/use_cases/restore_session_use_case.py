from datetime import timezone

from tkd_scorer.application.dto.session_dto import RestoreSessionInput, RestoreSessionOutput
from tkd_scorer.domain.entities.common import SessionStatus
from tkd_scorer.domain.exceptions.errors import UnauthorizedError
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort
from tkd_scorer.ports.security.token_service_port import TokenServicePort


class RestoreSessionUseCase:
    def __init__(
        self,
        *,
        session_repository: SessionRepositoryPort,
        token_service: TokenServicePort,
        clock: ClockPort,
    ) -> None:
        self._session_repository = session_repository
        self._token_service = token_service
        self._clock = clock

    def execute(self, request: RestoreSessionInput) -> RestoreSessionOutput:
        claims = self._token_service.parse_access_token(request.access_token)
        token_hash = self._token_service.hash_token(request.access_token)
        session = self._session_repository.get_by_token_hash(token_hash)
        if session is None:
            raise UnauthorizedError("Session not found")

        if session.status != SessionStatus.ACTIVE and not request.allow_inactive:
            raise UnauthorizedError("Session is not active")

        if session.expires_at:
            expires_at = session.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            now = self._clock.now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if expires_at < now:
                raise UnauthorizedError("Session expired")

        if session.id != claims.get("session_id"):
            raise UnauthorizedError("Session token mismatch")

        return RestoreSessionOutput(
            session_id=session.id,
            station_id=session.station_id,
            judge_name=session.judge_name,
            expires_at=session.expires_at,
            status=session.status.value,
        )
