from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tkd_scorer.infra.persistence.base import Base


class StationModel(Base):
    __tablename__ = "stations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Fernet token of the PIN (see adapters/security/credential_cipher.py). Databases from older versions
    # also have a credential_plain column; create_schema encrypts it into this one and clears it.
    credential_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_judge_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceSessionModel(Base):
    __tablename__ = "device_sessions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), nullable=False)
    judge_name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_id: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scorecard_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class MatchModel(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(ForeignKey("device_sessions.id"), nullable=False)
    judge_name: Mapped[str] = mapped_column(String(120), nullable=False)
    competitor_left_name: Mapped[str] = mapped_column(String(120), nullable=False)
    competitor_right_name: Mapped[str] = mapped_column(String(120), nullable=False)
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False)
    starting_score: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    judges_required: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # JSON lists of scorecard identities (session IDs): counted judges and judges removed by the operator.
    judge_session_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    removed_session_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")


class MatchRoundModel(Base):
    __tablename__ = "match_rounds"
    __table_args__ = (UniqueConstraint("match_id", "round_number", name="uq_match_round"),)

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScoreEventModel(Base):
    __tablename__ = "score_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_score_event_idempotency"),
        UniqueConstraint("event_id", name="uq_score_event_event_id"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(140), nullable=False)
    event_id: Mapped[str] = mapped_column(String(140), nullable=False)
    session_id: Mapped[str] = mapped_column(ForeignKey("device_sessions.id"), nullable=False)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), nullable=False)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    athlete_side: Mapped[str] = mapped_column(String(10), nullable=False)
    # NULL for events stored before score targets were persisted (technique).
    score_target: Mapped[str | None] = mapped_column(String(40), nullable=True)
    score_delta: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    score_before: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    score_after: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    judge_name: Mapped[str] = mapped_column(String(120), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    key: Mapped[str] = mapped_column(String(140), unique=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    response_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FinalizationRecordModel(Base):
    __tablename__ = "finalization_records"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(140), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    station_id: Mapped[str] = mapped_column(String(64), nullable=False)
    match_id: Mapped[str] = mapped_column(String(100), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reconciliation_notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    round_numbers: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    response_payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(120), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
