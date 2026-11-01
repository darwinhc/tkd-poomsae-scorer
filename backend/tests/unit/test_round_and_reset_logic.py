from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import RealtimeRecorderAdapter
from tkd_scorer.application.dto.score_dto import IngestScoreEventInput
from tkd_scorer.application.use_cases.control_match_use_cases import (
    NextRoundUseCase,
    ResetMatchUseCase,
    ResetRoundUseCase,
)
from tkd_scorer.application.use_cases.ingest_score_event_use_case import IngestScoreEventUseCase
from tkd_scorer.domain.entities.common import RoundStatus
from tkd_scorer.domain.entities.match import MatchRound
from tkd_scorer.domain.exceptions.errors import ValidationError


@pytest.mark.asyncio
async def test_next_round_moves_to_second_round_and_blocks_after_limit(fixture_bundle) -> None:
    realtime = RealtimeRecorderAdapter()
    use_case = NextRoundUseCase(
        match_repository=fixture_bundle["matches"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )

    ack = await use_case.execute("match-1", "admin")

    assert ack.message == "Round advanced"
    assert fixture_bundle["matches"].get_match("match-1").current_round == 2

    with pytest.raises(ValidationError):
        await use_case.execute("match-1", "admin")


@pytest.mark.asyncio
async def test_reset_round_and_reset_match_clear_events(fixture_bundle) -> None:
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
            athlete_side="blue",
            score_delta=Decimal("-0.1"),
            occurred_at=datetime(2026, 3, 18, 12, 1, tzinfo=timezone.utc),
            sequence=1,
            judge_name="Judge 1",
        )
    )

    reset_round = ResetRoundUseCase(
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )
    await reset_round.execute("match-1", "admin")
    assert fixture_bundle["score_events"].list_for_match("match-1") == []

    fixture_bundle["matches"].upsert_round(
        MatchRound(
            id="round-2",
            match_id="match-1",
            round_number=1,
            status=RoundStatus.ACTIVE,
            started_at=fixture_bundle["clock"].now(),
        )
    )

    await ingest.execute(
        IngestScoreEventInput(
            event_id="event-2",
            idempotency_key="idem-2",
            session_id="sess-1",
            station_id="station-01",
            match_id="match-1",
            round_number=1,
            athlete_side="red",
            score_delta=Decimal("-0.1"),
            occurred_at=datetime(2026, 3, 18, 12, 2, tzinfo=timezone.utc),
            sequence=2,
            judge_name="Judge 1",
        )
    )

    reset_match = ResetMatchUseCase(
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        realtime=realtime,
        clock=fixture_bundle["clock"],
        id_generator=fixture_bundle["ids"],
    )
    await reset_match.execute("match-1", "admin")

    assert fixture_bundle["score_events"].list_for_match("match-1") == []
    assert fixture_bundle["matches"].get_match("match-1").current_round == 1
