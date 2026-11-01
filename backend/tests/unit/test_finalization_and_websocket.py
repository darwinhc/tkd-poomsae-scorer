from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tkd_scorer.adapters.checksum.sha256_checksum_service import Sha256ChecksumService
from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import RealtimeRecorderAdapter
from tkd_scorer.application.dto.match_dto import FinalizeMatchInput
from tkd_scorer.application.dto.score_dto import IngestScoreEventInput
from tkd_scorer.application.use_cases._datetime_format import to_iso_utc_z
from tkd_scorer.application.use_cases.finalize_match_use_case import FinalizeMatchUseCase
from tkd_scorer.application.use_cases.ingest_score_event_use_case import IngestScoreEventUseCase
from tkd_scorer.domain.entities.common import SessionStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.exceptions.errors import ValidationError
from tkd_scorer.domain.services.finalization_checksum import build_finalize_checksum_payload
from tkd_scorer.domain.services.judge_scorecard import RoundScore


def _canonical_checksum(*, total_events: int, last_sequence: int, rounds: list[RoundScore]) -> str:
    # Same payload the judge app hashes (judge-app/src/domain/services/checksum.ts).
    technique_red = sum((item.technique_red for item in rounds), Decimal("0")) / len(rounds)
    presentation_red = sum((item.presentation_red for item in rounds), Decimal("0")) / len(rounds)
    technique_blue = sum((item.technique_blue for item in rounds), Decimal("0")) / len(rounds)
    presentation_blue = sum((item.presentation_blue for item in rounds), Decimal("0")) / len(rounds)
    return Sha256ChecksumService().compute(
        build_finalize_checksum_payload(
            match_id="match-1",
            session_id="sess-1",
            station_id="station-01",
            judge_name="Judge 1",
            total_events=total_events,
            last_sequence=last_sequence,
            final_score_red=technique_red + presentation_red,
            final_score_blue=technique_blue + presentation_blue,
            rounds=rounds,
        )
    )


def _rounds_summary(rounds: list[RoundScore]) -> list[dict]:
    return [
        {
            "roundNumber": item.round_number,
            "techniqueRed": float(item.technique_red),
            "presentationRed": float(item.presentation_red),
            "techniqueBlue": float(item.technique_blue),
            "presentationBlue": float(item.presentation_blue),
            "red": float(item.technique_red + item.presentation_red),
            "blue": float(item.technique_blue + item.presentation_blue),
        }
        for item in rounds
    ]


@pytest.mark.asyncio
async def test_finalization_reconciliation_and_duplicate_handling(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    ingest = IngestScoreEventUseCase(
        idempotency_repository=fixture_bundle["idempotency"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    await ingest.execute(
        IngestScoreEventInput(
            event_id="event-1",
            idempotency_key="idem-1",
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side="red",
            score_delta=Decimal("-0.1"),
            occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            sequence=1,
            judge_name="Judge 1",
        )
    )

    checksum_service = Sha256ChecksumService()
    rounds = [
        RoundScore(
            round_number=1,
            technique_red=Decimal("3.9"),
            presentation_red=Decimal("6.0"),
            technique_blue=Decimal("4.0"),
            presentation_blue=Decimal("6.0"),
        )
    ]
    checksum = _canonical_checksum(total_events=1, last_sequence=1, rounds=rounds)

    finalize = FinalizeMatchUseCase(
        finalization_repository=fixture_bundle["finalizations"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        session_repository=fixture_bundle["sessions"],
        station_repository=fixture_bundle["stations"],
        checksum_service=checksum_service,
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    request = FinalizeMatchInput(
        session_id="sess-1",
        station_id="station-01",
        match_id="match-1",
        judge_name="Judge 1",
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        total_rounds=2,
        final_round=1,
        final_score_left=Decimal("9.9"),
        final_score_right=Decimal("10.0"),
        total_events=1,
        last_sequence=1,
        started_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 3, 18, 12, 10, tzinfo=timezone.utc),
        checksum=checksum,
        idempotency_key="fin-1",
        rounds_summary=_rounds_summary(rounds),
    )

    first = await finalize.execute(request)
    duplicate = await finalize.execute(request)

    assert first.reconciled is True, first.notes
    assert first.checksum_verified is True
    assert first.server_final_score_left == Decimal("9.90")
    assert first.match_status == "finished"
    assert duplicate.idempotent_replay is True
    assert duplicate.reconciled is True
    assert duplicate.server_final_score_left == first.server_final_score_left
    assert any(item["event_type"] == "session_revoked" for item in realtime.events if "event_type" in item)
    active_state_events = [item for item in realtime.events if item.get("event_type") == "active_match_state"]
    assert active_state_events
    assert active_state_events[-1]["payload"]["hasActiveMatch"] is False
    assert active_state_events[-1]["payload"]["matchId"] == "match-1"


@pytest.mark.asyncio
async def test_finalization_checksum_mismatch_sets_pending_state(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    finalize = FinalizeMatchUseCase(
        finalization_repository=fixture_bundle["finalizations"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        session_repository=fixture_bundle["sessions"],
        station_repository=fixture_bundle["stations"],
        checksum_service=Sha256ChecksumService(),
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    result = await finalize.execute(
        FinalizeMatchInput(
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            judge_name="Judge 1",
            competitor_left_name="Competitor A",
            competitor_right_name="Competitor B",
            total_rounds=2,
            final_round=1,
            final_score_left=Decimal("10.0"),
            final_score_right=Decimal("10.0"),
            total_events=0,
            last_sequence=0,
            started_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 3, 18, 12, 10, tzinfo=timezone.utc),
            checksum="invalid",
            idempotency_key="fin-2",
        )
    )

    assert result.reconciled is False
    assert "checksum mismatch" in result.notes


@pytest.mark.asyncio
async def test_finalization_resolves_match_by_session_when_client_match_id_differs(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    finalize = FinalizeMatchUseCase(
        finalization_repository=fixture_bundle["finalizations"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        session_repository=fixture_bundle["sessions"],
        station_repository=fixture_bundle["stations"],
        checksum_service=Sha256ChecksumService(),
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    with pytest.raises(ValidationError, match="matchId must reference an existing backend match"):
        await finalize.execute(
            FinalizeMatchInput(
                session_id="sess-1",
                station_id="station-01",
                match_id="mobile-local-match-id",
                judge_name="Judge 1",
                competitor_left_name="Competitor A",
                competitor_right_name="Competitor B",
                total_rounds=2,
                final_round=1,
                final_score_left=Decimal("10.0"),
                final_score_right=Decimal("10.0"),
                total_events=0,
                last_sequence=0,
                started_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 3, 18, 12, 10, tzinfo=timezone.utc),
                checksum="invalid",
                idempotency_key="fin-fallback-by-session",
            )
        )


@pytest.mark.asyncio
async def test_finalization_rejects_checksum_of_the_reported_legacy_payload(fixture_bundle) -> None:
    # The old checksum modes hashed the client's own payload (verified integrity only, never matched the app).
    # Only the canonical scorecard payload rebuilt by the server is accepted now.
    realtime = RealtimeRecorderAdapter()
    checksum_service = Sha256ChecksumService()
    finalize = FinalizeMatchUseCase(
        finalization_repository=fixture_bundle["finalizations"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        session_repository=fixture_bundle["sessions"],
        station_repository=fixture_bundle["stations"],
        checksum_service=checksum_service,
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )
    started_at = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 3, 18, 12, 10, tzinfo=timezone.utc)
    rounds_summary = [
        {"roundNumber": 1, "finalScoreRed": "10.0", "finalScoreBlue": "10.0"},
    ]
    checksum_payload = {
        "sessionId": "sess-1",
        "stationId": "station-01",
        "matchId": "match-1",
        "judgeName": "Judge 1",
        "competitorLeftName": "Competitor A",
        "competitorRightName": "Competitor B",
        "totalRounds": 2,
        "finalRound": 1,
        "finalScoreRed": "10.0",
        "finalScoreBlue": "10.0",
        "totalEvents": 0,
        "finalSequence": 0,
        "startedAt": to_iso_utc_z(started_at),
        "finishedAt": to_iso_utc_z(finished_at),
        "roundsSummary": rounds_summary,
    }
    checksum = checksum_service.compute(checksum_payload)

    result = await finalize.execute(
        FinalizeMatchInput(
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            judge_name="Judge 1",
            competitor_left_name="Competitor A",
            competitor_right_name="Competitor B",
            total_rounds=2,
            final_round=1,
            final_score_left=Decimal("10.0"),
            final_score_right=Decimal("10.0"),
            total_events=0,
            last_sequence=0,
            started_at=started_at,
            finished_at=finished_at,
            checksum=checksum,
            idempotency_key="fin-reported-checksum",
            rounds_summary=rounds_summary,
        )
    )

    assert result.reconciled is False
    assert result.checksum_verified is False
    assert result.checksum_mode == "mismatch"
    assert "checksum mismatch" in result.notes


@pytest.mark.asyncio
async def test_finalization_keeps_station_occupied_if_other_judge_session_is_active(
    fixture_bundle,
) -> None:
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
    checksum_service = Sha256ChecksumService()
    realtime = RealtimeRecorderAdapter()
    finalize = FinalizeMatchUseCase(
        finalization_repository=fixture_bundle["finalizations"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        session_repository=fixture_bundle["sessions"],
        station_repository=fixture_bundle["stations"],
        checksum_service=checksum_service,
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    rounds = [
        RoundScore(
            round_number=1,
            technique_red=Decimal("4.0"),
            presentation_red=Decimal("6.0"),
            technique_blue=Decimal("4.0"),
            presentation_blue=Decimal("6.0"),
        )
    ]
    checksum = _canonical_checksum(total_events=0, last_sequence=0, rounds=rounds)
    result = await finalize.execute(
        FinalizeMatchInput(
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            judge_name="Judge 1",
            competitor_left_name="Competitor A",
            competitor_right_name="Competitor B",
            total_rounds=2,
            final_round=1,
            final_score_left=Decimal("10.0"),
            final_score_right=Decimal("10.0"),
            total_events=0,
            last_sequence=0,
            started_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 3, 18, 12, 10, tzinfo=timezone.utc),
            checksum=checksum,
            idempotency_key="fin-keep-occupied",
            rounds_summary=_rounds_summary(rounds),
        )
    )

    assert result.reconciled is True, result.notes
    station = fixture_bundle["stations"].get_by_id("station-01")
    assert station is not None
    assert station.status.value == "occupied"
    assert station.active_session_id == "sess-2"
