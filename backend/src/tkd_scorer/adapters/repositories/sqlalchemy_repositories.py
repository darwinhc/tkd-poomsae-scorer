from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

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
from tkd_scorer.infra.persistence.models import (
    AuditEventModel,
    DeviceSessionModel,
    FinalizationRecordModel,
    IdempotencyRecordModel,
    MatchModel,
    MatchRoundModel,
    ScoreEventModel,
    StationModel,
)
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.finalization_repository_port import FinalizationRepositoryPort
from tkd_scorer.ports.repositories.idempotency_repository_port import IdempotencyRepositoryPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.score_event_repository_port import ScoreEventRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort
from tkd_scorer.ports.repositories.station_repository_port import StationRepositoryPort


class SqlAlchemyStationRepository(StationRepositoryPort):
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_all(self) -> list[Station]:
        rows = self._db.scalars(select(StationModel)).all()
        return [self._to_entity(item) for item in rows]

    def list_active(self) -> list[Station]:
        rows = self._db.scalars(
            select(StationModel).where(StationModel.status.in_([StationStatus.ACTIVE.value, StationStatus.OCCUPIED.value]))
        ).all()
        return [self._to_entity(item) for item in rows]

    def get_by_id(self, station_id: str) -> Station | None:
        row = self._db.get(StationModel, station_id)
        return self._to_entity(row) if row else None

    def save(self, station: Station) -> None:
        row = self._db.get(StationModel, station.id)
        if row is None:
            row = StationModel(id=station.id)
            self._db.add(row)
        row.name = station.name
        row.status = station.status.value
        row.credential_hash = station.credential_hash
        row.credential_encrypted = station.credential_encrypted
        row.credential_expires_at = station.credential_expires_at
        row.expected_judge_name = station.expected_judge_name
        row.active_session_id = station.active_session_id
        row.updated_at = station.updated_at
        self._db.flush()

    def delete(self, station_id: str) -> bool:
        has_sessions = bool(
            self._db.scalar(select(func.count(DeviceSessionModel.id)).where(DeviceSessionModel.station_id == station_id))
        )
        has_matches = bool(self._db.scalar(select(func.count(MatchModel.id)).where(MatchModel.station_id == station_id)))
        has_events = bool(
            self._db.scalar(select(func.count(ScoreEventModel.id)).where(ScoreEventModel.station_id == station_id))
        )
        if has_sessions or has_matches or has_events:
            return False

        result = self._db.execute(delete(StationModel).where(StationModel.id == station_id))
        self._db.flush()
        return bool(result.rowcount)

    @staticmethod
    def _to_entity(row: StationModel) -> Station:
        return Station(
            id=row.id,
            name=row.name,
            status=StationStatus(row.status),
            credential_hash=row.credential_hash,
            credential_encrypted=row.credential_encrypted,
            credential_expires_at=row.credential_expires_at,
            expected_judge_name=row.expected_judge_name,
            active_session_id=row.active_session_id,
            updated_at=row.updated_at,
        )


class SqlAlchemySessionRepository(SessionRepositoryPort):
    def __init__(self, db: Session) -> None:
        self._db = db

    def save(self, session: DeviceSession) -> None:
        row = self._db.get(DeviceSessionModel, session.id)
        if row is None:
            row = DeviceSessionModel(id=session.id)
            self._db.add(row)
        row.station_id = session.station_id
        row.judge_name = session.judge_name
        row.device_id = session.device_id
        row.token_hash = session.token_hash
        row.status = session.status.value
        row.created_at = session.created_at
        row.expires_at = session.expires_at
        row.revoked_at = session.revoked_at
        row.scorecard_session_id = session.scorecard_session_id
        self._db.flush()

    def get_by_id(self, session_id: str) -> DeviceSession | None:
        row = self._db.get(DeviceSessionModel, session_id)
        return self._to_entity(row) if row else None

    def get_by_token_hash(self, token_hash: str) -> DeviceSession | None:
        row = self._db.scalars(select(DeviceSessionModel).where(DeviceSessionModel.token_hash == token_hash)).first()
        return self._to_entity(row) if row else None

    def revoke(self, session_id: str) -> None:
        row = self._db.get(DeviceSessionModel, session_id)
        if row is not None:
            row.status = SessionStatus.REVOKED.value
            self._db.flush()

    def get_active_by_station(self, station_id: str) -> DeviceSession | None:
        row = self._db.scalars(
            select(DeviceSessionModel).where(
                DeviceSessionModel.station_id == station_id,
                DeviceSessionModel.status == SessionStatus.ACTIVE.value,
            )
            .order_by(DeviceSessionModel.created_at.desc())
        ).first()
        return self._to_entity(row) if row else None

    def list_active_by_station(self, station_id: str) -> list[DeviceSession]:
        rows = self._db.scalars(
            select(DeviceSessionModel).where(
                DeviceSessionModel.station_id == station_id,
                DeviceSessionModel.status == SessionStatus.ACTIVE.value,
            )
            .order_by(DeviceSessionModel.created_at.desc())
        ).all()
        return [self._to_entity(item) for item in rows]

    def list_active(self) -> list[DeviceSession]:
        rows = self._db.scalars(
            select(DeviceSessionModel).where(DeviceSessionModel.status == SessionStatus.ACTIVE.value)
        ).all()
        return [self._to_entity(item) for item in rows]

    @staticmethod
    def _to_entity(row: DeviceSessionModel) -> DeviceSession:
        return DeviceSession(
            id=row.id,
            station_id=row.station_id,
            judge_name=row.judge_name,
            device_id=row.device_id,
            token_hash=row.token_hash,
            status=SessionStatus(row.status),
            created_at=row.created_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            scorecard_session_id=row.scorecard_session_id,
        )


class SqlAlchemyMatchRepository(MatchRepositoryPort):
    def __init__(self, db: Session) -> None:
        self._db = db

    def save_match(self, match: Match) -> None:
        row = self._db.get(MatchModel, match.id)
        if row is None:
            row = MatchModel(id=match.id)
            self._db.add(row)
        row.station_id = match.station_id
        row.session_id = match.session_id
        row.judge_name = match.judge_name
        row.competitor_left_name = match.competitor_left_name
        row.competitor_right_name = match.competitor_right_name
        row.total_rounds = match.total_rounds
        row.current_round = match.current_round
        row.starting_score = match.starting_score
        row.status = match.status.value
        row.created_at = match.created_at
        row.started_at = match.started_at
        row.finished_at = match.finished_at
        row.judges_required = max(1, int(match.judges_required))
        row.judge_session_ids = json.dumps(list(match.judge_session_ids))
        row.removed_session_ids = json.dumps(list(match.removed_session_ids))
        self._db.flush()

    def get_match(self, match_id: str) -> Match | None:
        row = self._db.get(MatchModel, match_id)
        if row is None:
            return None
        return self._to_entity(row)

    def upsert_round(self, round_entity: MatchRound) -> None:
        row = self._db.scalars(
            select(MatchRoundModel).where(
                MatchRoundModel.match_id == round_entity.match_id,
                MatchRoundModel.round_number == round_entity.round_number,
            )
        ).first()
        if row is None:
            row = MatchRoundModel(id=round_entity.id)
            self._db.add(row)
        row.match_id = round_entity.match_id
        row.round_number = round_entity.round_number
        row.status = round_entity.status.value
        row.started_at = round_entity.started_at
        row.ended_at = round_entity.ended_at
        self._db.flush()

    def get_round(self, match_id: str, round_number: int) -> MatchRound | None:
        row = self._db.scalars(
            select(MatchRoundModel).where(
                MatchRoundModel.match_id == match_id,
                MatchRoundModel.round_number == round_number,
            )
        ).first()
        if row is None:
            return None
        return MatchRound(
            id=row.id,
            match_id=row.match_id,
            round_number=row.round_number,
            status=RoundStatus(row.status),
            started_at=row.started_at,
            ended_at=row.ended_at,
        )

    def list_recent(self, *, limit: int, statuses: list[str] | None = None) -> list[Match]:
        if statuses:
            query = (
                select(MatchModel)
                .where(MatchModel.status.in_(statuses))
                .order_by(MatchModel.created_at.desc())
                .limit(limit)
            )
        else:
            query = select(MatchModel).order_by(MatchModel.created_at.desc()).limit(limit)
        rows = self._db.scalars(query).all()
        return [self._to_entity(item) for item in rows]

    def delete_match(self, match_id: str) -> bool:
        self._db.execute(delete(ScoreEventModel).where(ScoreEventModel.match_id == match_id))
        self._db.execute(delete(MatchRoundModel).where(MatchRoundModel.match_id == match_id))
        self._db.execute(delete(FinalizationRecordModel).where(FinalizationRecordModel.match_id == match_id))
        self._db.execute(delete(AuditEventModel).where(AuditEventModel.subject_id == match_id))
        result = self._db.execute(delete(MatchModel).where(MatchModel.id == match_id))
        self._db.flush()
        return bool(result.rowcount)

    @staticmethod
    def _to_entity(row: MatchModel) -> Match:
        return Match(
            id=row.id,
            station_id=row.station_id,
            session_id=row.session_id,
            judge_name=row.judge_name,
            competitor_left_name=row.competitor_left_name,
            competitor_right_name=row.competitor_right_name,
            total_rounds=row.total_rounds,
            current_round=row.current_round,
            starting_score=Decimal(row.starting_score),
            status=MatchStatus(row.status),
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            judges_required=max(1, int(row.judges_required or 1)),
            judge_session_ids=_parse_string_list(row.judge_session_ids),
            removed_session_ids=_parse_string_list(row.removed_session_ids),
        )


class SqlAlchemyScoreEventRepository(ScoreEventRepositoryPort):
    def __init__(self, db: Session) -> None:
        self._db = db

    def save(self, event: ScoreEvent) -> None:
        row = ScoreEventModel(
            id=event.id,
            idempotency_key=event.idempotency_key,
            event_id=event.event_id,
            session_id=event.session_id,
            station_id=event.station_id,
            match_id=event.match_id,
            round_number=event.round_number,
            athlete_side=event.athlete_side.value,
            score_target=event.score_target.value,
            score_delta=event.score_delta,
            score_before=event.score_before,
            score_after=event.score_after,
            occurred_at=event.occurred_at,
            sequence=event.sequence,
            judge_name=event.judge_name,
            received_at=event.received_at,
            processed_at=event.processed_at,
        )
        self._db.add(row)
        self._db.flush()

    def list_for_match(self, match_id: str) -> list[ScoreEvent]:
        rows = self._db.scalars(
            select(ScoreEventModel).where(ScoreEventModel.match_id == match_id).order_by(ScoreEventModel.sequence.asc())
        ).all()
        return [self._to_entity(item) for item in rows]

    def list_for_match_round(self, match_id: str, round_number: int) -> list[ScoreEvent]:
        rows = self._db.scalars(
            select(ScoreEventModel)
            .where(
                ScoreEventModel.match_id == match_id,
                ScoreEventModel.round_number == round_number,
            )
            .order_by(ScoreEventModel.sequence.asc())
        ).all()
        return [self._to_entity(item) for item in rows]

    def delete_for_match_round(self, match_id: str, round_number: int) -> None:
        self._db.execute(
            delete(ScoreEventModel).where(
                ScoreEventModel.match_id == match_id,
                ScoreEventModel.round_number == round_number,
            )
        )
        self._db.flush()

    def delete_for_match(self, match_id: str) -> None:
        self._db.execute(delete(ScoreEventModel).where(ScoreEventModel.match_id == match_id))
        self._db.flush()

    def get_last_sequence(self, match_id: str) -> int:
        value = self._db.scalar(
            select(func.max(ScoreEventModel.sequence)).where(ScoreEventModel.match_id == match_id)
        )
        return int(value or 0)

    def get_latest_score(
        self,
        match_id: str,
        side: AthleteSide,
        round_number: int,
        default: Decimal,
    ) -> Decimal:
        row = self._db.scalars(
            select(ScoreEventModel)
            .where(
                ScoreEventModel.match_id == match_id,
                ScoreEventModel.athlete_side == side.value,
                ScoreEventModel.round_number == round_number,
            )
            .order_by(ScoreEventModel.sequence.desc())
        ).first()
        if row is None:
            return default
        return Decimal(row.score_after)

    @staticmethod
    def _to_entity(row: ScoreEventModel) -> ScoreEvent:
        return ScoreEvent(
            id=row.id,
            idempotency_key=row.idempotency_key,
            event_id=row.event_id,
            session_id=row.session_id,
            station_id=row.station_id,
            match_id=row.match_id,
            round_number=row.round_number,
            athlete_side=AthleteSide(row.athlete_side),
            score_delta=Decimal(row.score_delta),
            score_before=Decimal(row.score_before),
            score_after=Decimal(row.score_after),
            occurred_at=row.occurred_at,
            sequence=row.sequence,
            judge_name=row.judge_name,
            received_at=row.received_at,
            processed_at=row.processed_at,
            score_target=ScoreTarget(row.score_target) if row.score_target else ScoreTarget.TECHNIQUE,
        )


class SqlAlchemyIdempotencyRepository(IdempotencyRepositoryPort):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, key: str) -> IdempotencyRecord | None:
        row = self._db.scalars(select(IdempotencyRecordModel).where(IdempotencyRecordModel.key == key)).first()
        if row is None:
            return None
        return IdempotencyRecord(
            id=row.id,
            key=row.key,
            operation=row.operation,
            response_payload=row.response_payload,
            created_at=row.created_at,
        )

    def save(self, record: IdempotencyRecord) -> None:
        row = IdempotencyRecordModel(
            id=record.id,
            key=record.key,
            operation=record.operation,
            response_payload=record.response_payload,
            created_at=record.created_at,
        )
        self._db.add(row)
        self._db.flush()


class SqlAlchemyFinalizationRepository(FinalizationRepositoryPort):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_idempotency_key(self, idempotency_key: str) -> FinalizationRecord | None:
        row = self._db.scalars(
            select(FinalizationRecordModel).where(FinalizationRecordModel.idempotency_key == idempotency_key)
        ).first()
        if row is None:
            return None
        return self._to_entity(row)

    def save(self, record: FinalizationRecord) -> None:
        row = FinalizationRecordModel(
            id=record.id,
            idempotency_key=record.idempotency_key,
            session_id=record.session_id,
            station_id=record.station_id,
            match_id=record.match_id,
            checksum=record.checksum,
            status=record.status,
            reconciliation_notes=record.reconciliation_notes,
            created_at=record.created_at,
            round_numbers=json.dumps([int(item) for item in record.round_numbers]),
            response_payload=record.response_payload or "{}",
        )
        self._db.add(row)
        self._db.flush()

    def delete_for_match(self, match_id: str) -> None:
        self._db.execute(delete(FinalizationRecordModel).where(FinalizationRecordModel.match_id == match_id))
        self._db.flush()

    def list_for_match(self, match_id: str) -> list[FinalizationRecord]:
        rows = self._db.scalars(
            select(FinalizationRecordModel)
            .where(FinalizationRecordModel.match_id == match_id)
            .order_by(FinalizationRecordModel.created_at.asc())
        ).all()
        return [self._to_entity(item) for item in rows]

    @staticmethod
    def _to_entity(row: FinalizationRecordModel) -> FinalizationRecord:
        return FinalizationRecord(
            id=row.id,
            idempotency_key=row.idempotency_key,
            session_id=row.session_id,
            station_id=row.station_id,
            match_id=row.match_id,
            checksum=row.checksum,
            status=row.status,
            reconciliation_notes=row.reconciliation_notes,
            created_at=row.created_at,
            round_numbers=_parse_round_numbers(row.round_numbers),
            response_payload="" if row.response_payload in (None, "{}") else row.response_payload,
        )


class SqlAlchemyAuditRepository(AuditRepositoryPort):
    def __init__(self, db: Session) -> None:
        self._db = db

    def save(self, event: AuditEvent) -> None:
        row = AuditEventModel(
            id=event.id,
            category=event.category,
            action=event.action,
            subject_id=event.subject_id,
            actor=event.actor,
            details=event.details,
            occurred_at=event.occurred_at,
        )
        self._db.add(row)
        self._db.flush()

    def list_recent(
        self,
        *,
        limit: int,
        category: str | None = None,
        action: str | None = None,
        subject_id: str | None = None,
    ) -> list[AuditEvent]:
        query = select(AuditEventModel)
        if category is not None:
            query = query.where(AuditEventModel.category == category)
        if action is not None:
            query = query.where(AuditEventModel.action == action)
        if subject_id is not None:
            query = query.where(AuditEventModel.subject_id == subject_id)

        rows = self._db.scalars(query.order_by(AuditEventModel.occurred_at.desc()).limit(limit)).all()
        return [
            AuditEvent(
                id=row.id,
                category=row.category,
                action=row.action,
                subject_id=row.subject_id,
                actor=row.actor,
                details=row.details,
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]


def _parse_round_numbers(raw: str | None) -> tuple[int, ...]:
    try:
        values = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return ()
    if not isinstance(values, list):
        return ()
    return tuple(int(item) for item in values if isinstance(item, int) and item > 0)


def _parse_string_list(raw: str | None) -> tuple[str, ...]:
    try:
        values = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return ()
    if not isinstance(values, list):
        return ()
    return tuple(str(item) for item in values if isinstance(item, str) and item)
