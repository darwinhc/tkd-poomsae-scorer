from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import SessionStatus, StationStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.entities.match import Match, MatchRound
from tkd_scorer.domain.entities.score_event import FinalizationRecord, IdempotencyRecord, ScoreEvent
from tkd_scorer.domain.entities.station import Station
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.finalization_repository_port import FinalizationRepositoryPort
from tkd_scorer.ports.repositories.idempotency_repository_port import IdempotencyRepositoryPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.score_event_repository_port import ScoreEventRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort
from tkd_scorer.ports.repositories.station_repository_port import StationRepositoryPort
from tkd_scorer.ports.security.credential_cipher_port import CredentialCipherPort
from tkd_scorer.ports.security.station_credential_service_port import StationCredentialServicePort
from tkd_scorer.ports.security.token_service_port import TokenServicePort


class FixedClock(ClockPort):
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        self._now += timedelta(milliseconds=1)
        return self._now


class SequentialIdGenerator(IdGeneratorPort):
    def __init__(self) -> None:
        self._counter = 0

    def new(self, prefix: str | None = None) -> str:
        self._counter += 1
        if prefix:
            return f"{prefix}-{self._counter}"
        return str(self._counter)


class PlainTokenService(TokenServicePort):
    def issue_access_token(self, *, session_id: str, station_id: str, judge_name: str) -> str:
        return f"{session_id}|{station_id}|{judge_name}"

    def parse_access_token(self, token: str) -> dict[str, str]:
        session_id, station_id, judge_name = token.split("|", maxsplit=2)
        return {
            "session_id": session_id,
            "station_id": station_id,
            "judge_name": judge_name,
        }

    def hash_token(self, token: str) -> str:
        return f"hash::{token}"


class PlainCredentialService(StationCredentialServicePort):
    def verify(self, plain_credential: str, credential_hash: str) -> bool:
        return plain_credential == credential_hash

    def hash_credential(self, plain_credential: str) -> str:
        return plain_credential


class InMemoryStationRepository(StationRepositoryPort):
    def __init__(self, stations: list[Station] | None = None) -> None:
        self.items = {item.id: item for item in (stations or [])}

    def list_all(self) -> list[Station]:
        return list(self.items.values())

    def list_active(self) -> list[Station]:
        return [
            item
            for item in self.items.values()
            if item.status in (StationStatus.ACTIVE, StationStatus.OCCUPIED)
        ]

    def get_by_id(self, station_id: str) -> Station | None:
        return self.items.get(station_id)

    def save(self, station: Station) -> None:
        self.items[station.id] = station

    def delete(self, station_id: str) -> bool:
        return self.items.pop(station_id, None) is not None


class InMemorySessionRepository(SessionRepositoryPort):
    def __init__(self) -> None:
        self.items: dict[str, DeviceSession] = {}

    def save(self, session: DeviceSession) -> None:
        self.items[session.id] = session

    def get_by_id(self, session_id: str) -> DeviceSession | None:
        return self.items.get(session_id)

    def get_by_token_hash(self, token_hash: str) -> DeviceSession | None:
        for item in self.items.values():
            if item.token_hash == token_hash:
                return item
        return None

    def revoke(self, session_id: str) -> None:
        item = self.items.get(session_id)
        if item:
            item.status = SessionStatus.REVOKED

    def get_active_by_station(self, station_id: str) -> DeviceSession | None:
        active = self.list_active_by_station(station_id)
        return active[0] if active else None

    def list_active_by_station(self, station_id: str) -> list[DeviceSession]:
        items = [
            item
            for item in self.items.values()
            if item.station_id == station_id and item.status == SessionStatus.ACTIVE
        ]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def list_active(self) -> list[DeviceSession]:
        return [item for item in self.items.values() if item.status == SessionStatus.ACTIVE]


class InMemoryMatchRepository(MatchRepositoryPort):
    def __init__(self) -> None:
        self.matches: dict[str, Match] = {}
        self.rounds: dict[tuple[str, int], MatchRound] = {}

    def save_match(self, match: Match) -> None:
        self.matches[match.id] = match

    def get_match(self, match_id: str) -> Match | None:
        return self.matches.get(match_id)

    def upsert_round(self, round_entity: MatchRound) -> None:
        self.rounds[(round_entity.match_id, round_entity.round_number)] = round_entity

    def get_round(self, match_id: str, round_number: int) -> MatchRound | None:
        return self.rounds.get((match_id, round_number))

    def list_recent(self, *, limit: int, statuses: list[str] | None = None) -> list[Match]:
        items = sorted(self.matches.values(), key=lambda item: item.created_at, reverse=True)
        if statuses:
            items = [item for item in items if item.status.value in statuses]
        return items[:limit]

    def delete_match(self, match_id: str) -> bool:
        deleted = self.matches.pop(match_id, None) is not None
        for key in list(self.rounds.keys()):
            if key[0] == match_id:
                self.rounds.pop(key, None)
        return deleted


class InMemoryScoreEventRepository(ScoreEventRepositoryPort):
    def __init__(self) -> None:
        self.events: list[ScoreEvent] = []

    def save(self, event: ScoreEvent) -> None:
        self.events.append(event)

    def list_for_match(self, match_id: str) -> list[ScoreEvent]:
        return sorted([item for item in self.events if item.match_id == match_id], key=lambda x: x.sequence)

    def list_for_match_round(self, match_id: str, round_number: int) -> list[ScoreEvent]:
        return [
            item
            for item in sorted(self.events, key=lambda x: x.sequence)
            if item.match_id == match_id and item.round_number == round_number
        ]

    def delete_for_match_round(self, match_id: str, round_number: int) -> None:
        self.events = [
            item
            for item in self.events
            if not (item.match_id == match_id and item.round_number == round_number)
        ]

    def delete_for_match(self, match_id: str) -> None:
        self.events = [item for item in self.events if item.match_id != match_id]

    def get_last_sequence(self, match_id: str) -> int:
        values = [item.sequence for item in self.events if item.match_id == match_id]
        return max(values) if values else 0

    def get_latest_score(self, match_id: str, side, round_number: int, default: Decimal) -> Decimal:
        candidates = [
            item
            for item in self.events
            if item.match_id == match_id and item.athlete_side == side and item.round_number == round_number
        ]
        if not candidates:
            return default
        return sorted(candidates, key=lambda x: x.sequence)[-1].score_after


class InMemoryIdempotencyRepository(IdempotencyRepositoryPort):
    def __init__(self) -> None:
        self.items: dict[str, IdempotencyRecord] = {}

    def get(self, key: str) -> IdempotencyRecord | None:
        return self.items.get(key)

    def save(self, record: IdempotencyRecord) -> None:
        self.items[record.key] = record


class InMemoryFinalizationRepository(FinalizationRepositoryPort):
    def __init__(self) -> None:
        self.items: dict[str, FinalizationRecord] = {}

    def get_by_idempotency_key(self, idempotency_key: str) -> FinalizationRecord | None:
        return self.items.get(idempotency_key)

    def save(self, record: FinalizationRecord) -> None:
        self.items[record.idempotency_key] = record

    def list_for_match(self, match_id: str) -> list[FinalizationRecord]:
        return sorted(
            [item for item in self.items.values() if item.match_id == match_id],
            key=lambda item: item.created_at,
        )

    def delete_for_match(self, match_id: str) -> None:
        self.items = {key: item for key, item in self.items.items() if item.match_id != match_id}


class InMemoryAuditRepository(AuditRepositoryPort):
    def __init__(self) -> None:
        self.items: list[AuditEvent] = []

    def save(self, event: AuditEvent) -> None:
        self.items.append(event)

    def list_recent(
        self,
        *,
        limit: int,
        category: str | None = None,
        action: str | None = None,
        subject_id: str | None = None,
    ) -> list[AuditEvent]:
        items = sorted(self.items, key=lambda item: item.occurred_at, reverse=True)
        if category is not None:
            items = [item for item in items if item.category == category]
        if action is not None:
            items = [item for item in items if item.action == action]
        if subject_id is not None:
            items = [item for item in items if item.subject_id == subject_id]
        return items[:limit]


@dataclass
class UseCaseFixture:
    clock: FixedClock
    ids: SequentialIdGenerator
    token_service: PlainTokenService
    credential_service: PlainCredentialService
    stations: InMemoryStationRepository
    sessions: InMemorySessionRepository
    matches: InMemoryMatchRepository
    score_events: InMemoryScoreEventRepository
    idempotency: InMemoryIdempotencyRepository
    finalizations: InMemoryFinalizationRepository
    audit: InMemoryAuditRepository


class ReversibleCredentialCipher(CredentialCipherPort):
    """Test cipher: reversible, and decryption fails for values written with another key."""

    def __init__(self, key: str = "test-key") -> None:
        self._prefix = f"enc[{key}]:"

    def encrypt(self, plain_credential: str) -> str:
        return f"{self._prefix}{plain_credential[::-1]}"

    def decrypt(self, encrypted_credential: str) -> str | None:
        if not encrypted_credential.startswith(self._prefix):
            return None
        return encrypted_credential[len(self._prefix) :][::-1]
