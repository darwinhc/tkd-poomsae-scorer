from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.unit.fakes import (
    FixedClock,
    InMemoryAuditRepository,
    InMemoryFinalizationRepository,
    InMemoryIdempotencyRepository,
    InMemoryMatchRepository,
    InMemoryScoreEventRepository,
    InMemorySessionRepository,
    InMemoryStationRepository,
    PlainCredentialService,
    PlainTokenService,
    SequentialIdGenerator,
)
from tkd_scorer.domain.entities.common import MatchStatus, RoundStatus, SessionStatus, StationStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.entities.match import Match, MatchRound
from tkd_scorer.domain.entities.station import Station


@pytest.fixture
def fixture_bundle():
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
    matches = InMemoryMatchRepository()
    score_events = InMemoryScoreEventRepository()
    idempotency = InMemoryIdempotencyRepository()
    finalizations = InMemoryFinalizationRepository()
    audit = InMemoryAuditRepository()
    clock = FixedClock(datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc))
    ids = SequentialIdGenerator()
    token_service = PlainTokenService()
    credential_service = PlainCredentialService()

    session = DeviceSession(
        id="sess-1",
        station_id="station-01",
        judge_name="Judge 1",
        device_id="device-1",
        token_hash=token_service.hash_token("sess-1|station-01|Judge 1"),
        status=SessionStatus.ACTIVE,
        created_at=clock.now(),
        expires_at=clock.now(),
    )
    sessions.save(session)

    match = Match(
        id="match-1",
        station_id="station-01",
        session_id="sess-1",
        judge_name="Judge 1",
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        total_rounds=2,
        current_round=1,
        starting_score=Decimal("4.0"),
        status=MatchStatus.IN_PROGRESS,
        created_at=clock.now(),
        started_at=clock.now(),
    )
    matches.save_match(match)
    matches.upsert_round(
        MatchRound(
            id="round-1",
            match_id="match-1",
            round_number=1,
            status=RoundStatus.ACTIVE,
            started_at=clock.now(),
        )
    )

    return {
        "stations": stations,
        "sessions": sessions,
        "matches": matches,
        "score_events": score_events,
        "idempotency": idempotency,
        "finalizations": finalizations,
        "audit": audit,
        "clock": clock,
        "ids": ids,
        "token_service": token_service,
        "credential_service": credential_service,
    }
