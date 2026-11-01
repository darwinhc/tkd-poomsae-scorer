from datetime import datetime, timezone

import pytest

from tests.unit.fakes import FixedClock, InMemorySessionRepository, PlainTokenService
from tkd_scorer.adapters.security.system_services import JwtTokenService
from tkd_scorer.application.dto.session_dto import RestoreSessionInput
from tkd_scorer.application.use_cases.restore_session_use_case import RestoreSessionUseCase
from tkd_scorer.domain.entities.common import SessionStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.exceptions.errors import UnauthorizedError


def test_restore_session_with_plain_token_service() -> None:
    token_service = PlainTokenService()
    sessions = InMemorySessionRepository()
    token = token_service.issue_access_token(
        session_id="sess-1",
        station_id="station-01",
        judge_name="Judge 1",
    )
    sessions.save(
        DeviceSession(
            id="sess-1",
            station_id="station-01",
            judge_name="Judge 1",
            device_id="device-1",
            token_hash=token_service.hash_token(token),
            status=SessionStatus.ACTIVE,
            created_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
            expires_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )
    )

    use_case = RestoreSessionUseCase(
        session_repository=sessions,
        token_service=token_service,
        clock=FixedClock(datetime(2026, 3, 18, tzinfo=timezone.utc)),
    )

    result = use_case.execute(RestoreSessionInput(access_token=token))

    assert result.session_id == "sess-1"
    assert result.judge_name == "Judge 1"


def test_jwt_token_service_raises_on_invalid_token() -> None:
    service = JwtTokenService(secret_key="secret", algorithm="HS256", token_ttl_seconds=3600)

    with pytest.raises(UnauthorizedError):
        service.parse_access_token("invalid.token")
