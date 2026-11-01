from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tkd_scorer.adapters.checksum.sha256_checksum_service import Sha256ChecksumService
from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import RealtimeRecorderAdapter
from tkd_scorer.application.dto.match_dto import FinalizeMatchInput
from tkd_scorer.application.dto.score_dto import IngestScoreEventInput
from tkd_scorer.application.use_cases.finalize_match_use_case import FinalizeMatchUseCase
from tkd_scorer.application.use_cases.get_station_active_match_state_use_case import (
    GetStationActiveMatchStateUseCase,
)
from tkd_scorer.application.use_cases.ingest_score_event_use_case import IngestScoreEventUseCase
from tkd_scorer.domain.entities.common import MatchStatus, SessionStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.exceptions.errors import UnauthorizedError
from tkd_scorer.domain.services.finalization_checksum import build_finalize_checksum_payload
from tkd_scorer.domain.services.judge_scorecard import RoundScore

_START = datetime(2026, 3, 18, 11, 0, tzinfo=timezone.utc)
_JUDGES = {"sess-1": "Judge 1", "sess-2": "Judge 2", "sess-3": "Judge 3"}


@pytest.fixture
def three_judges(fixture_bundle):
    sessions = fixture_bundle["sessions"]
    sessions.items["sess-1"].created_at = _START
    for index, session_id in enumerate(("sess-2", "sess-3"), start=1):
        sessions.save(
            DeviceSession(
                id=session_id,
                station_id="station-01",
                judge_name=_JUDGES[session_id],
                device_id=f"device-{index + 1}",
                token_hash=f"hash::{session_id}",
                status=SessionStatus.ACTIVE,
                created_at=_START + timedelta(minutes=index),
                expires_at=None,
            )
        )
    match = fixture_bundle["matches"].get_match("match-1")
    match.judges_required = 3
    fixture_bundle["matches"].save_match(match)
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
    return {**fixture_bundle, "ingest": ingest, "finalize": finalize, "realtime": realtime}


async def _score(bundle, session_id: str, sequence: int, delta: str, target: str = "TECHNIQUE", side: str = "red"):
    return await bundle["ingest"].execute(
        IngestScoreEventInput(
            event_id=f"{session_id}-event-{sequence}",
            idempotency_key=f"{session_id}-idem-{sequence}",
            session_id=session_id,
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side=side,
            score_delta=Decimal(delta),
            occurred_at=_START,
            sequence=sequence,
            judge_name=_JUDGES[session_id],
            score_target=target,
        )
    )


def _finalize_input(session_id: str, technique_red: str, *, total_events: int, last_sequence: int, key: str):
    round_one = RoundScore(
        round_number=1,
        technique_red=Decimal(technique_red),
        presentation_red=Decimal("6.0"),
        technique_blue=Decimal("4.0"),
        presentation_blue=Decimal("6.0"),
    )
    final_red = Decimal(technique_red) + Decimal("6.0")
    checksum = Sha256ChecksumService().compute(
        build_finalize_checksum_payload(
            match_id="match-1",
            session_id=session_id,
            station_id="station-01",
            judge_name=_JUDGES[session_id],
            total_events=total_events,
            last_sequence=last_sequence,
            final_score_red=final_red,
            final_score_blue=Decimal("10.0"),
            rounds=[round_one],
        )
    )
    return FinalizeMatchInput(
        session_id=session_id,
        station_id="station-01",
        match_id="match-1",
        judge_name=_JUDGES[session_id],
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        total_rounds=2,
        final_round=1,
        final_score_left=final_red,
        final_score_right=Decimal("10.0"),
        total_events=total_events,
        last_sequence=last_sequence,
        started_at=_START,
        finished_at=_START,
        checksum=checksum,
        idempotency_key=key,
        rounds_summary=[
            {
                "roundNumber": 1,
                "techniqueRed": float(technique_red),
                "presentationRed": 6.0,
                "techniqueBlue": 4.0,
                "presentationBlue": 6.0,
            }
        ],
    )


@pytest.mark.asyncio
async def test_running_scores_are_per_judge_and_per_target(three_judges) -> None:
    first = await _score(three_judges, "sess-1", 1, "-0.3")
    # Same sequence number from another judge is a different event, not a conflict.
    other = await _score(three_judges, "sess-2", 1, "-0.1")
    presentation = await _score(three_judges, "sess-1", 2, "-0.2", target="PRESENTATION_SPEED_POWER")
    second = await _score(three_judges, "sess-1", 3, "-0.1")

    assert (first.score_before, first.score_after) == (Decimal("4.0"), Decimal("3.7"))
    assert (other.score_before, other.score_after) == (Decimal("4.0"), Decimal("3.9"))
    assert (presentation.score_before, presentation.score_after) == (Decimal("2.0"), Decimal("1.8"))
    assert (second.score_before, second.score_after) == (Decimal("3.7"), Decimal("3.6"))
    assert len(three_judges["score_events"].events) == 4


@pytest.mark.asyncio
async def test_shared_match_closes_only_after_every_judge_finalizes(three_judges) -> None:
    await _score(three_judges, "sess-1", 1, "-0.3")
    await _score(three_judges, "sess-2", 1, "-0.1")
    await _score(three_judges, "sess-3", 1, "-0.2")
    matches = three_judges["matches"]
    state = GetStationActiveMatchStateUseCase(
        station_repository=three_judges["stations"],
        session_repository=three_judges["sessions"],
        match_repository=matches,
        clock=three_judges["clock"],
    )

    first = await three_judges["finalize"].execute(
        _finalize_input("sess-1", "3.7", total_events=1, last_sequence=1, key="fin-sess-1")
    )
    assert first.reconciled is True, first.notes
    assert first.match_status == MatchStatus.IN_PROGRESS.value
    assert (first.judges_finalized, first.judges_required) == (1, 3)
    assert matches.get_match("match-1").status == MatchStatus.IN_PROGRESS
    # Judge 1 is released, the shared match stays active for judges 2 and 3.
    assert three_judges["sessions"].get_by_id("sess-1").status == SessionStatus.REVOKED
    assert state.execute("station-01").has_active_match is True
    assert not any(
        item["event_type"] == "active_match_state" for item in three_judges["realtime"].events
    )

    second = await three_judges["finalize"].execute(
        _finalize_input("sess-2", "3.9", total_events=1, last_sequence=1, key="fin-sess-2")
    )
    assert second.reconciled is True, second.notes
    assert matches.get_match("match-1").status == MatchStatus.IN_PROGRESS

    third = await three_judges["finalize"].execute(
        _finalize_input("sess-3", "3.8", total_events=1, last_sequence=1, key="fin-sess-3")
    )
    assert third.reconciled is True, third.notes
    assert third.match_status == MatchStatus.FINISHED.value
    assert matches.get_match("match-1").status == MatchStatus.FINISHED
    active_state = [item for item in three_judges["realtime"].events if item["event_type"] == "active_match_state"]
    assert active_state[-1]["payload"]["hasActiveMatch"] is False


@pytest.mark.asyncio
async def test_same_judge_finalizing_again_replays_the_first_response(three_judges) -> None:
    await _score(three_judges, "sess-1", 1, "-0.3")
    first = await three_judges["finalize"].execute(
        _finalize_input("sess-1", "3.7", total_events=1, last_sequence=1, key="fin-a")
    )
    # New idempotency key, released session: still the stored answer, never a 422.
    again = _finalize_input("sess-1", "3.7", total_events=1, last_sequence=1, key="fin-b")
    replay = await three_judges["finalize"].execute(
        replace(again, session_active=False)
    )

    assert replay.idempotent_replay is True
    assert (replay.status, replay.reconciled, replay.notes) == (first.status, first.reconciled, first.notes)
    assert replay.server_final_score_left == first.server_final_score_left
    assert replay.match_status == first.match_status
    assert len(three_judges["finalizations"].items) == 1


@pytest.mark.asyncio
async def test_released_session_cannot_finalize_without_a_previous_finalization(three_judges) -> None:
    request = _finalize_input("sess-2", "4.0", total_events=0, last_sequence=0, key="fin-released")
    with pytest.raises(UnauthorizedError):
        await three_judges["finalize"].execute(replace(request, session_active=False))


@pytest.mark.asyncio
async def test_unreconciled_judge_leaves_the_match_pending_after_all_finalize(three_judges) -> None:
    await _score(three_judges, "sess-1", 1, "-0.3")
    for session_id, technique in (("sess-1", "3.7"), ("sess-2", "4.0")):
        events = 1 if session_id == "sess-1" else 0
        result = await three_judges["finalize"].execute(
            _finalize_input(session_id, technique, total_events=events, last_sequence=events, key=f"fin-{session_id}")
        )
        assert result.reconciled is True, result.notes

    # Judge 3 reports a deduction the server never received.
    mismatch = await three_judges["finalize"].execute(
        _finalize_input("sess-3", "3.5", total_events=1, last_sequence=1, key="fin-sess-3")
    )

    assert mismatch.reconciled is False
    assert "checksum mismatch" in mismatch.notes
    assert "totalEvents mismatch" in mismatch.notes
    assert mismatch.status == MatchStatus.FINALIZATION_PENDING.value
    assert mismatch.match_status == MatchStatus.FINALIZATION_PENDING.value
    assert three_judges["sessions"].get_by_id("sess-3").status == SessionStatus.ACTIVE
