from datetime import datetime, timezone

import pytest

from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import RealtimeRecorderAdapter
from tkd_scorer.application.use_cases.kick_judge_session_use_case import KickJudgeSessionUseCase
from tkd_scorer.domain.entities.common import SessionStatus, StationStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.exceptions.errors import NotFoundError


@pytest.mark.asyncio
async def test_kick_judge_session_revokes_session_and_emits_ws_events(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    station = fixture_bundle["stations"].get_by_id("station-01")
    assert station is not None
    station.status = StationStatus.OCCUPIED
    station.active_session_id = "sess-1"
    fixture_bundle["stations"].save(station)

    use_case = KickJudgeSessionUseCase(
        session_repository=fixture_bundle["sessions"],
        station_repository=fixture_bundle["stations"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    result = await use_case.execute(
        station_id="station-01",
        session_id="sess-1",
        reason="operator_replaced",
        actor="local-admin",
    )

    assert result.status == "revoked"
    assert result.remaining_active_sessions == 0
    kicked = fixture_bundle["sessions"].get_by_id("sess-1")
    assert kicked is not None
    assert kicked.status == SessionStatus.REVOKED

    station_after = fixture_bundle["stations"].get_by_id("station-01")
    assert station_after is not None
    assert station_after.status == StationStatus.ACTIVE
    assert station_after.active_session_id is None

    emitted_types = [item["event_type"] for item in realtime.events]
    assert "judge_kicked" in emitted_types
    assert "session_revoked" in emitted_types


@pytest.mark.asyncio
async def test_kick_judge_session_keeps_station_occupied_when_other_judge_is_active(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    fixture_bundle["sessions"].save(
        DeviceSession(
            id="sess-2",
            station_id="station-01",
            judge_name="Judge 3",
            device_id="device-2",
            token_hash="hash::sess-2",
            status=SessionStatus.ACTIVE,
            created_at=datetime(2026, 3, 18, 12, 1, tzinfo=timezone.utc),
            expires_at=None,
        )
    )
    station = fixture_bundle["stations"].get_by_id("station-01")
    assert station is not None
    station.status = StationStatus.OCCUPIED
    station.active_session_id = "sess-2"
    fixture_bundle["stations"].save(station)

    use_case = KickJudgeSessionUseCase(
        session_repository=fixture_bundle["sessions"],
        station_repository=fixture_bundle["stations"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    result = await use_case.execute(
        station_id="station-01",
        session_id="sess-1",
        reason="operator_replaced",
        actor="local-admin",
    )

    assert result.remaining_active_sessions == 1
    station_after = fixture_bundle["stations"].get_by_id("station-01")
    assert station_after is not None
    assert station_after.status == StationStatus.OCCUPIED
    assert station_after.active_session_id == "sess-2"


@pytest.mark.asyncio
async def test_kick_judge_session_raises_when_session_not_found(fixture_bundle) -> None:
    use_case = KickJudgeSessionUseCase(
        session_repository=fixture_bundle["sessions"],
        station_repository=fixture_bundle["stations"],
        audit_repository=fixture_bundle["audit"],
        realtime=RealtimeRecorderAdapter(),
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    with pytest.raises(NotFoundError):
        await use_case.execute(
            station_id="station-01",
            session_id="sess-404",
            reason="operator_replaced",
            actor="local-admin",
        )
