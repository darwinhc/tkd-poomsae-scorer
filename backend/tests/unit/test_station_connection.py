from datetime import datetime, timezone

import pytest

from tests.unit.fakes import (
    FixedClock,
    InMemoryAuditRepository,
    InMemorySessionRepository,
    InMemoryStationRepository,
    PlainCredentialService,
    PlainTokenService,
    SequentialIdGenerator,
)
from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import RealtimeRecorderAdapter
from tkd_scorer.application.dto.station_dto import ConnectStationInput
from tkd_scorer.application.use_cases.connect_station_use_case import ConnectStationUseCase
from tkd_scorer.domain.entities.common import SessionStatus, StationStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.entities.station import Station
from tkd_scorer.domain.exceptions.errors import ConflictError


def _build_use_case(
    stations: InMemoryStationRepository,
    sessions: InMemorySessionRepository,
    *,
    realtime: RealtimeRecorderAdapter | None = None,
) -> ConnectStationUseCase:
    return ConnectStationUseCase(
        station_repository=stations,
        session_repository=sessions,
        audit_repository=InMemoryAuditRepository(),
        credential_service=PlainCredentialService(),
        token_service=PlainTokenService(),
        clock=FixedClock(datetime(2026, 3, 18, tzinfo=timezone.utc)),
        id_generator=SequentialIdGenerator(),
        session_ttl_seconds=3600,
        realtime=realtime,
    )


@pytest.mark.asyncio
async def test_connect_station_binds_judge_and_returns_session_token() -> None:
    stations = InMemoryStationRepository(
        [
            Station(
                id="station-01",
                name="Station 01",
                status=StationStatus.ACTIVE,
                credential_hash="1234",
            )
        ]
    )
    sessions = InMemorySessionRepository()
    use_case = _build_use_case(stations, sessions)

    result = await use_case.execute(
        ConnectStationInput(
            station_id="station-01",
            judge_name="Judge 1",
            credential="1234",
            device_id="device-1",
        )
    )

    assert result.session_id.startswith("sess-")
    assert result.station.active_session_id == result.session_id
    stored = sessions.get_by_id(result.session_id)
    assert stored is not None
    assert stored.judge_name == "Judge 1"


@pytest.mark.asyncio
async def test_connect_station_allows_multiple_active_judges_in_same_station() -> None:
    stations = InMemoryStationRepository(
        [
            Station(
                id="station-01",
                name="Station 01",
                status=StationStatus.ACTIVE,
                credential_hash="1234",
            )
        ]
    )
    sessions = InMemorySessionRepository()
    use_case = _build_use_case(stations, sessions)

    first = await use_case.execute(
        ConnectStationInput(
            station_id="station-01",
            judge_name="Judge 1",
            credential="1234",
            device_id="device-1",
        )
    )
    second = await use_case.execute(
        ConnectStationInput(
            station_id="station-01",
            judge_name="Judge 3",
            credential="1234",
            device_id="device-2",
        )
    )

    assert first.session_id != second.session_id
    assert len(sessions.list_active_by_station("station-01")) == 2


@pytest.mark.asyncio
async def test_connect_station_rejects_same_judge_with_different_device() -> None:
    stations = InMemoryStationRepository(
        [
            Station(
                id="station-01",
                name="Station 01",
                status=StationStatus.OCCUPIED,
                credential_hash="1234",
                active_session_id="sess-existing",
            )
        ]
    )
    sessions = InMemorySessionRepository()
    sessions.save(
        DeviceSession(
            id="sess-existing",
            station_id="station-01",
            judge_name="Judge 1",
            device_id="device-1",
            token_hash="hash::existing",
            status=SessionStatus.ACTIVE,
            created_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
            expires_at=None,
        )
    )
    use_case = _build_use_case(stations, sessions)

    with pytest.raises(ConflictError):
        await use_case.execute(
            ConnectStationInput(
                station_id="station-01",
                judge_name="Judge 1",
                credential="1234",
                device_id="device-2",
            )
        )


@pytest.mark.asyncio
async def test_connect_station_rejects_same_device_with_different_judge() -> None:
    stations = InMemoryStationRepository(
        [
            Station(
                id="station-01",
                name="Station 01",
                status=StationStatus.OCCUPIED,
                credential_hash="1234",
                active_session_id="sess-existing",
            )
        ]
    )
    sessions = InMemorySessionRepository()
    sessions.save(
        DeviceSession(
            id="sess-existing",
            station_id="station-01",
            judge_name="Judge 1",
            device_id="device-1",
            token_hash="hash::existing",
            status=SessionStatus.ACTIVE,
            created_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
            expires_at=None,
        )
    )
    use_case = _build_use_case(stations, sessions)

    with pytest.raises(ConflictError):
        await use_case.execute(
            ConnectStationInput(
                station_id="station-01",
                judge_name="Another Judge",
                credential="1234",
                device_id="device-1",
            )
        )


def _station_with_active_judge() -> tuple[InMemoryStationRepository, InMemorySessionRepository]:
    stations = InMemoryStationRepository(
        [
            Station(
                id="station-01",
                name="Station 01",
                status=StationStatus.OCCUPIED,
                credential_hash="1234",
                active_session_id="sess-existing",
            )
        ]
    )
    sessions = InMemorySessionRepository()
    sessions.save(
        DeviceSession(
            id="sess-existing",
            station_id="station-01",
            judge_name="Judge 1",
            device_id="device-1",
            token_hash="hash::existing",
            status=SessionStatus.ACTIVE,
            created_at=datetime(2026, 3, 17, tzinfo=timezone.utc),
            expires_at=None,
        )
    )
    return stations, sessions


@pytest.mark.asyncio
async def test_replacing_the_judge_session_on_another_device_revokes_and_notifies_the_old_one() -> None:
    stations, sessions = _station_with_active_judge()
    realtime = RealtimeRecorderAdapter()
    use_case = _build_use_case(stations, sessions, realtime=realtime)

    result = await use_case.execute(
        ConnectStationInput(
            station_id="station-01",
            judge_name="Judge 1",
            credential="1234",
            device_id="device-2",
            replace_existing_judge_session=True,
        )
    )

    assert sessions.get_by_id("sess-existing").status == SessionStatus.REVOKED
    new_session = sessions.get_by_id(result.session_id)
    assert new_session.status == SessionStatus.ACTIVE
    # The new session continues the old scorecard: one judge, its events keep counting.
    assert new_session.scorecard_key == "sess-existing"
    notified = {(item["session_id"], item["event_type"]) for item in realtime.events}
    assert notified == {("sess-existing", "judge_kicked"), ("sess-existing", "session_revoked")}
    assert all(item["payload"]["sessionId"] == "sess-existing" for item in realtime.events)


@pytest.mark.asyncio
async def test_same_device_reconnection_continues_the_scorecard_without_notifying() -> None:
    stations, sessions = _station_with_active_judge()
    realtime = RealtimeRecorderAdapter()
    use_case = _build_use_case(stations, sessions, realtime=realtime)

    result = await use_case.execute(
        ConnectStationInput(station_id="station-01", judge_name="Judge 1", credential="1234", device_id="device-1")
    )

    assert sessions.get_by_id(result.session_id).scorecard_key == "sess-existing"
    assert realtime.events == []
