from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import RealtimeRecorderAdapter
from tkd_scorer.application.dto.score_dto import IngestScoreEventInput
from tkd_scorer.application.use_cases.ingest_score_event_use_case import IngestScoreEventUseCase
from tkd_scorer.domain.exceptions.errors import ValidationError
from tkd_scorer.domain.services.scoring import compute_score


@pytest.mark.asyncio
async def test_score_event_ingestion_is_idempotent(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    use_case = IngestScoreEventUseCase(
        idempotency_repository=fixture_bundle["idempotency"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    request = IngestScoreEventInput(
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

    first = await use_case.execute(request)
    second = await use_case.execute(request)

    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert len(fixture_bundle["score_events"].events) == 1


@pytest.mark.asyncio
async def test_score_event_ingestion_requires_existing_backend_match_id(
    fixture_bundle,
) -> None:
    realtime = RealtimeRecorderAdapter()
    use_case = IngestScoreEventUseCase(
        idempotency_repository=fixture_bundle["idempotency"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    with pytest.raises(ValidationError, match="matchId must reference an existing backend match"):
        await use_case.execute(
            IngestScoreEventInput(
                event_id="event-stale-1",
                idempotency_key="idem-stale-1",
                session_id="sess-1",
                station_id="station-01",
                match_id="match-inexistente",
                round_number=1,
                athlete_side="blue",
                score_delta=Decimal("-0.1"),
                occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
                sequence=1,
                judge_name="Judge 1",
            )
        )
    assert len(fixture_bundle["score_events"].events) == 0


@pytest.mark.asyncio
async def test_score_event_ingestion_accepts_accumulated_score_delta(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    use_case = IngestScoreEventUseCase(
        idempotency_repository=fixture_bundle["idempotency"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    result = await use_case.execute(
        IngestScoreEventInput(
            event_id="event-acc-1",
            idempotency_key="idem-acc-1",
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side="red",
            score_delta=Decimal("-0.8"),
            occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            sequence=1,
            judge_name="Judge 1",
        )
    )

    assert result.idempotent_replay is False
    assert fixture_bundle["score_events"].events[0].score_delta == Decimal("-0.8")


@pytest.mark.asyncio
async def test_score_event_ingestion_accepts_out_of_order_sequences(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    use_case = IngestScoreEventUseCase(
        idempotency_repository=fixture_bundle["idempotency"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    await use_case.execute(
        IngestScoreEventInput(
            event_id="event-out-3",
            idempotency_key="idem-out-3",
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side="red",
            score_delta=Decimal("-0.1"),
            occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            sequence=3,
            judge_name="Judge 1",
        )
    )
    await use_case.execute(
        IngestScoreEventInput(
            event_id="event-out-1",
            idempotency_key="idem-out-1",
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side="red",
            score_delta=Decimal("-0.2"),
            occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            sequence=1,
            judge_name="Judge 1",
        )
    )
    await use_case.execute(
        IngestScoreEventInput(
            event_id="event-out-2",
            idempotency_key="idem-out-2",
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side="red",
            score_delta=Decimal("0.1"),
            occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            sequence=2,
            judge_name="Judge 1",
        )
    )

    events = fixture_bundle["score_events"].list_for_match("match-1")
    red_events = [item for item in events if item.athlete_side.value == "red" and item.round_number == 1]
    assert len(red_events) == 3
    assert compute_score(Decimal("10.0"), red_events) == Decimal("9.8")


@pytest.mark.asyncio
async def test_score_event_ingestion_replays_by_sequence_when_payload_matches(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    use_case = IngestScoreEventUseCase(
        idempotency_repository=fixture_bundle["idempotency"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    first = await use_case.execute(
        IngestScoreEventInput(
            event_id="event-seq-1",
            idempotency_key="idem-seq-1",
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side="blue",
            score_delta=Decimal("-0.1"),
            occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            sequence=10,
            judge_name="Judge 1",
        )
    )

    replay = await use_case.execute(
        IngestScoreEventInput(
            event_id="event-seq-1-replayed",
            idempotency_key="idem-seq-1-replayed",
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side="blue",
            score_delta=Decimal("-0.1"),
            occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            sequence=10,
            judge_name="Judge 1",
        )
    )

    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert replay.sequence == 10
    assert len(fixture_bundle["score_events"].events) == 1


@pytest.mark.asyncio
async def test_score_event_ingestion_rejects_sequence_conflict_when_payload_differs(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    use_case = IngestScoreEventUseCase(
        idempotency_repository=fixture_bundle["idempotency"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    await use_case.execute(
        IngestScoreEventInput(
            event_id="event-conflict-1",
            idempotency_key="idem-conflict-1",
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side="red",
            score_delta=Decimal("-0.1"),
            occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            sequence=11,
            judge_name="Judge 1",
        )
    )

    with pytest.raises(ValidationError, match="Sequence already exists"):
        await use_case.execute(
            IngestScoreEventInput(
                event_id="event-conflict-2",
                idempotency_key="idem-conflict-2",
                session_id="sess-1",
                station_id="station-01",
                match_id="match-1",
                round_number=1,
                athlete_side="red",
                score_delta=Decimal("-0.3"),
                occurred_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
                sequence=11,
                judge_name="Judge 1",
            )
        )


@pytest.mark.asyncio
async def test_score_event_for_a_closed_match_is_rejected_with_match_closed(fixture_bundle) -> None:
    from tkd_scorer.domain.entities.common import MatchStatus
    from tkd_scorer.domain.exceptions.errors import MatchClosedError

    match = fixture_bundle["matches"].get_match("match-1")
    match.status = MatchStatus.FINISHED
    fixture_bundle["matches"].save_match(match)
    use_case = IngestScoreEventUseCase(
        idempotency_repository=fixture_bundle["idempotency"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=RealtimeRecorderAdapter(),
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    with pytest.raises(MatchClosedError) as raised:
        await use_case.execute(
            IngestScoreEventInput(
                event_id="event-late",
                idempotency_key="idem-late",
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
    assert raised.value.code == "match_closed"
    assert fixture_bundle["score_events"].events == []
