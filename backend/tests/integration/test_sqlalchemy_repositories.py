from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from tkd_scorer.adapters.repositories.sqlalchemy_repositories import (
    SqlAlchemyAuditRepository,
    SqlAlchemyFinalizationRepository,
    SqlAlchemyIdempotencyRepository,
    SqlAlchemyMatchRepository,
    SqlAlchemyScoreEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyStationRepository,
)
from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import (
    AthleteSide,
    MatchStatus,
    RoundStatus,
    ScoreTarget,
    SessionStatus,
    StationStatus,
)
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.entities.match import Match, MatchRound
from tkd_scorer.domain.entities.score_event import FinalizationRecord, IdempotencyRecord, ScoreEvent
from tkd_scorer.domain.entities.station import Station
from tkd_scorer.infra.persistence.base import Base
from tkd_scorer.infra.persistence.session_factory import create_schema


def test_sqlalchemy_repository_roundtrip() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        stations = SqlAlchemyStationRepository(db)
        sessions = SqlAlchemySessionRepository(db)
        matches = SqlAlchemyMatchRepository(db)
        score_events = SqlAlchemyScoreEventRepository(db)
        idempotency = SqlAlchemyIdempotencyRepository(db)
        finalizations = SqlAlchemyFinalizationRepository(db)
        audit = SqlAlchemyAuditRepository(db)

        station = Station(
            id="station-01",
            name="Station 01",
            status=StationStatus.ACTIVE,
            credential_hash="hash",
        )
        stations.save(station)

        session = DeviceSession(
            id="sess-1",
            station_id="station-01",
            judge_name="Judge 1",
            device_id="dev-1",
            token_hash="token-hash",
            status=SessionStatus.ACTIVE,
            created_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
            expires_at=None,
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
            starting_score=Decimal("10.0"),
            status=MatchStatus.IN_PROGRESS,
            created_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
        )
        matches.save_match(match)
        matches.upsert_round(
            MatchRound(
                id="round-1",
                match_id="match-1",
                round_number=1,
                status=RoundStatus.ACTIVE,
                started_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
            )
        )

        score_events.save(
            ScoreEvent(
                id="score-1",
                idempotency_key="idem-score-1",
                event_id="event-1",
                session_id="sess-1",
                station_id="station-01",
                match_id="match-1",
                round_number=1,
                athlete_side=AthleteSide.RED,
                score_delta=Decimal("-0.1"),
                score_before=Decimal("10.0"),
                score_after=Decimal("9.9"),
                occurred_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
                sequence=1,
                judge_name="Judge 1",
                received_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
                processed_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
            )
        )

        idempotency.save(
            IdempotencyRecord(
                id="idem-1",
                key="idem-score-1",
                operation="score_event_ingestion",
                response_payload="{}",
                created_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
            )
        )

        finalizations.save(
            FinalizationRecord(
                id="fin-1",
                idempotency_key="final-1",
                session_id="sess-1",
                station_id="station-01",
                match_id="match-1",
                checksum="abc",
                status="finished",
                reconciliation_notes="ok",
                created_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
            )
        )

        audit.save(
            AuditEvent(
                id="audit-1",
                category="score",
                action="ingest",
                subject_id="score-1",
                actor="Judge 1",
                details="details",
                occurred_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
            )
        )

        db.commit()

        assert stations.get_by_id("station-01") is not None
        assert sessions.get_by_id("sess-1") is not None
        assert matches.get_match("match-1") is not None
        assert matches.get_round("match-1", 1) is not None
        assert score_events.get_last_sequence("match-1") == 1
        assert idempotency.get("idem-score-1") is not None
        assert finalizations.get_by_idempotency_key("final-1") is not None


def test_shared_match_fields_roundtrip() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    create_schema(engine)
    now = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)

    with Session(engine) as db:
        SqlAlchemyStationRepository(db).save(
            Station(id="station-01", name="Station 01", status=StationStatus.ACTIVE, credential_hash="x")
        )
        SqlAlchemySessionRepository(db).save(
            DeviceSession(
                id="sess-1",
                station_id="station-01",
                judge_name="Judge 1",
                device_id="device-1",
                token_hash="hash-1",
                status=SessionStatus.ACTIVE,
                created_at=now,
                expires_at=None,
            )
        )
        matches = SqlAlchemyMatchRepository(db)
        matches.save_match(
            Match(
                id="match-1",
                station_id="station-01",
                session_id="sess-1",
                judge_name="Judge 1",
                competitor_left_name="A",
                competitor_right_name="B",
                total_rounds=2,
                current_round=1,
                starting_score=Decimal("4.0"),
                status=MatchStatus.IN_PROGRESS,
                created_at=now,
                judges_required=5,
            )
        )
        score_events = SqlAlchemyScoreEventRepository(db)
        score_events.save(
            ScoreEvent(
                id="score-1",
                idempotency_key="idem-1",
                event_id="event-1",
                session_id="sess-1",
                station_id="station-01",
                match_id="match-1",
                round_number=1,
                athlete_side=AthleteSide.RED,
                score_delta=Decimal("-0.2"),
                score_before=Decimal("2.0"),
                score_after=Decimal("1.8"),
                occurred_at=now,
                sequence=1,
                judge_name="Judge 1",
                received_at=now,
                processed_at=now,
                score_target=ScoreTarget.PRESENTATION_RHYTHM_TEMPO,
            )
        )
        finalizations = SqlAlchemyFinalizationRepository(db)
        finalizations.save(
            FinalizationRecord(
                id="fin-1",
                idempotency_key="fin-key-1",
                session_id="sess-1",
                station_id="station-01",
                match_id="match-1",
                checksum="abc",
                status="finished",
                reconciliation_notes="reconciled",
                created_at=now,
                round_numbers=(1, 2),
                response_payload='{"status": "finished"}',
            )
        )
        db.commit()

        assert matches.get_match("match-1").judges_required == 5
        assert score_events.list_for_match("match-1")[0].score_target == ScoreTarget.PRESENTATION_RHYTHM_TEMPO
        stored = finalizations.list_for_match("match-1")
        assert [item.round_numbers for item in stored] == [(1, 2)]
        assert stored[0].response_payload == '{"status": "finished"}'


def test_create_schema_adds_new_columns_to_an_existing_database(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'old.db'}", future=True)
    with engine.begin() as connection:
        # Tables as created by the previous release (without the shared-match columns).
        connection.execute(
            text(
                "CREATE TABLE matches (id VARCHAR(100) PRIMARY KEY, station_id VARCHAR(64) NOT NULL, "
                "session_id VARCHAR(100) NOT NULL, judge_name VARCHAR(120) NOT NULL, "
                "competitor_left_name VARCHAR(120) NOT NULL, competitor_right_name VARCHAR(120) NOT NULL, "
                "total_rounds INTEGER NOT NULL, current_round INTEGER NOT NULL, starting_score NUMERIC(5, 1) NOT NULL, "
                "status VARCHAR(32) NOT NULL, created_at DATETIME NOT NULL, started_at DATETIME, finished_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO matches VALUES ('match-old', 'station-01', 'sess-1', 'Judge 1', 'A', 'B', 2, 1, 10.0, "
                "'finished', '2026-03-18 12:00:00', NULL, NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE score_events (id VARCHAR(100) PRIMARY KEY, idempotency_key VARCHAR(140) NOT NULL, "
                "event_id VARCHAR(140) NOT NULL, session_id VARCHAR(100) NOT NULL, station_id VARCHAR(64) NOT NULL, "
                "match_id VARCHAR(100) NOT NULL, round_number INTEGER NOT NULL, athlete_side VARCHAR(10) NOT NULL, "
                "score_delta NUMERIC(4, 1) NOT NULL, score_before NUMERIC(5, 1) NOT NULL, "
                "score_after NUMERIC(5, 1) NOT NULL, occurred_at DATETIME NOT NULL, sequence INTEGER NOT NULL, "
                "judge_name VARCHAR(120) NOT NULL, received_at DATETIME NOT NULL, processed_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE finalization_records (id VARCHAR(100) PRIMARY KEY, idempotency_key VARCHAR(140) NOT NULL, "
                "session_id VARCHAR(100) NOT NULL, station_id VARCHAR(64) NOT NULL, match_id VARCHAR(100) NOT NULL, "
                "checksum VARCHAR(128) NOT NULL, status VARCHAR(32) NOT NULL, reconciliation_notes TEXT NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )

    create_schema(engine)
    create_schema(engine)  # idempotent

    columns = {
        table: {column["name"] for column in inspect(engine).get_columns(table)}
        for table in ("matches", "score_events", "finalization_records")
    }
    assert {"judges_required", "judge_session_ids", "removed_session_ids"} <= columns["matches"]
    assert "score_target" in columns["score_events"]
    assert {"round_numbers", "response_payload"} <= columns["finalization_records"]
    with Session(engine) as db:
        legacy = SqlAlchemyMatchRepository(db).get_match("match-old")
        assert legacy is not None
        assert legacy.judges_required == 1
        assert legacy.judge_session_ids == ()
        assert legacy.removed_session_ids == ()


def test_judge_tracking_replacement_and_encrypted_credential_roundtrip() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    create_schema(engine)
    now = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)

    with Session(engine) as db:
        stations = SqlAlchemyStationRepository(db)
        sessions = SqlAlchemySessionRepository(db)
        matches = SqlAlchemyMatchRepository(db)
        finalizations = SqlAlchemyFinalizationRepository(db)
        stations.save(
            Station(
                id="station-01",
                name="Station 01",
                status=StationStatus.ACTIVE,
                credential_hash="hash",
                credential_encrypted="gAAAA-token",
            )
        )
        sessions.save(
            DeviceSession(
                id="sess-2",
                station_id="station-01",
                judge_name="Judge 1",
                device_id="dev-2",
                token_hash="token-2",
                status=SessionStatus.ACTIVE,
                created_at=now,
                expires_at=None,
                scorecard_session_id="sess-1",
            )
        )
        match = Match(
            id="match-1",
            station_id="station-01",
            session_id="sess-2",
            judge_name="Judge 1",
            competitor_left_name="A",
            competitor_right_name="B",
            total_rounds=2,
            current_round=1,
            starting_score=Decimal("4.0"),
            status=MatchStatus.IN_PROGRESS,
            created_at=now,
        )
        match.set_judges(["sess-1", "sess-3", "sess-4"])
        match.remove_judge("sess-4")
        matches.save_match(match)
        finalizations.save(
            FinalizationRecord(
                id="fin-1",
                idempotency_key="fin-key",
                session_id="sess-2",
                station_id="station-01",
                match_id="match-1",
                checksum="x",
                status="finished",
                reconciliation_notes="reconciled",
                created_at=now,
            )
        )
        db.commit()

        assert stations.get_by_id("station-01").credential_encrypted == "gAAAA-token"
        assert sessions.get_by_id("sess-2").scorecard_key == "sess-1"
        stored = matches.get_match("match-1")
        assert stored.judge_session_ids == ("sess-1", "sess-3", "sess-4")
        assert stored.removed_session_ids == ("sess-4",)
        assert stored.judges_required == 2
        finalizations.delete_for_match("match-1")
        assert finalizations.list_for_match("match-1") == []
