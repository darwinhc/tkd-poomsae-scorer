from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Generator
from urllib.parse import urlparse

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from tkd_scorer.adapters.checksum.sha256_checksum_service import Sha256ChecksumService
from tkd_scorer.adapters.qr.bootstrap_service import JwtBootstrapService
from tkd_scorer.adapters.repositories.sqlalchemy_repositories import (
    SqlAlchemyAuditRepository,
    SqlAlchemyFinalizationRepository,
    SqlAlchemyIdempotencyRepository,
    SqlAlchemyMatchRepository,
    SqlAlchemyScoreEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyStationRepository,
)
from tkd_scorer.adapters.security.credential_cipher import FernetCredentialCipher
from tkd_scorer.adapters.security.credential_generator import NumericCredentialGenerator
from tkd_scorer.adapters.security.system_clock_and_ids import UtcClock, UuidIdGenerator
from tkd_scorer.adapters.security.system_services import (
    JwtTokenService,
    PasswordStationCredentialService,
)
from tkd_scorer.application.use_cases.admin_view_use_cases import AdminViewUseCases
from tkd_scorer.application.use_cases.connect_station_use_case import ConnectStationUseCase
from tkd_scorer.application.use_cases.control_match_use_cases import (
    GetMatchSummaryUseCase,
    NextRoundUseCase,
    ResetMatchUseCase,
    ResetRoundUseCase,
)
from tkd_scorer.application.use_cases.create_match_use_case import CreateMatchUseCase
from tkd_scorer.application.use_cases.finalize_match_use_case import FinalizeMatchUseCase
from tkd_scorer.application.use_cases.generate_bootstrap_use_case import GenerateBootstrapUseCase
from tkd_scorer.application.use_cases.get_station_active_match_state_use_case import (
    GetStationActiveMatchStateUseCase,
)
from tkd_scorer.application.use_cases.get_station_active_session_use_case import (
    GetStationActiveSessionUseCase,
)
from tkd_scorer.application.use_cases.ingest_score_event_use_case import IngestScoreEventUseCase
from tkd_scorer.application.use_cases.kick_judge_session_use_case import KickJudgeSessionUseCase
from tkd_scorer.application.use_cases.list_active_stations_use_case import ListActiveStationsUseCase
from tkd_scorer.application.use_cases.restore_session_use_case import RestoreSessionUseCase
from tkd_scorer.application.use_cases.validate_bootstrap_use_case import ValidateBootstrapUseCase
from tkd_scorer.infra.config.runtime_base_url import resolve_qr_base_url
from tkd_scorer.infra.config.settings import Settings


@dataclass(frozen=True)
class Repositories:
    stations: SqlAlchemyStationRepository
    sessions: SqlAlchemySessionRepository
    matches: SqlAlchemyMatchRepository
    score_events: SqlAlchemyScoreEventRepository
    idempotency: SqlAlchemyIdempotencyRepository
    finalizations: SqlAlchemyFinalizationRepository
    audit: SqlAlchemyAuditRepository


@dataclass(frozen=True)
class UseCases:
    generate_bootstrap: GenerateBootstrapUseCase
    validate_bootstrap: ValidateBootstrapUseCase
    list_active_stations: ListActiveStationsUseCase
    connect_station: ConnectStationUseCase
    restore_session: RestoreSessionUseCase
    create_match: CreateMatchUseCase
    ingest_score_event: IngestScoreEventUseCase
    finalize_match: FinalizeMatchUseCase
    next_round: NextRoundUseCase
    reset_round: ResetRoundUseCase
    reset_match: ResetMatchUseCase
    match_summary: GetMatchSummaryUseCase
    station_active_session: GetStationActiveSessionUseCase
    station_active_match_state: GetStationActiveMatchStateUseCase


@dataclass(frozen=True)
class AdminUseCases:
    views: AdminViewUseCases
    kick_judge_session: KickJudgeSessionUseCase | None = None


def _qr_seed_base_url(settings: Settings) -> str:
    parsed = urlparse(settings.effective_public_base_url)
    scheme = parsed.scheme or "http"
    path = parsed.path.rstrip("/")
    port = int(settings.port)
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    host = "127.0.0.1"
    netloc = host if default_port else f"{host}:{port}"
    return f"{scheme}://{netloc}{path}"


def resolve_settings_qr_base_url(settings: Settings) -> str:
    """Base URL written into the QR bootstrap payload.

    - TKD_QR_SERVER_IP_OVERRIDE set: that IP (it wins over everything else), with the server's port and the
      scheme / path of the public URL.
    - otherwise TKD_QR_USE_SERVER_IP=true: the auto-detected LAN IP of the server, same port / scheme / path.
    - otherwise: TKD_PUBLIC_BASE_URL (or TKD_BASE_URL when unset) exactly as configured.
    """
    override = (settings.qr_server_ip_override or "").strip() or None
    if override is None and not settings.qr_use_server_ip:
        return resolve_qr_base_url(
            configured_base_url=settings.effective_public_base_url,
            use_server_ip=False,
            server_ip_override=None,
        )
    return resolve_qr_base_url(
        configured_base_url=_qr_seed_base_url(settings),
        use_server_ip=True,
        server_ip_override=override,
    )


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    db: Session = session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_repositories(db: Session = Depends(get_db_session)) -> Repositories:
    return Repositories(
        stations=SqlAlchemyStationRepository(db),
        sessions=SqlAlchemySessionRepository(db),
        matches=SqlAlchemyMatchRepository(db),
        score_events=SqlAlchemyScoreEventRepository(db),
        idempotency=SqlAlchemyIdempotencyRepository(db),
        finalizations=SqlAlchemyFinalizationRepository(db),
        audit=SqlAlchemyAuditRepository(db),
    )


def get_use_cases(
    request: Request,
    settings: Settings = Depends(get_settings),
    repositories: Repositories = Depends(get_repositories),
) -> UseCases:
    clock = UtcClock()
    id_generator = UuidIdGenerator()
    token_service = JwtTokenService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        token_ttl_seconds=settings.operational_token_ttl_seconds,
    )
    bootstrap_service = JwtBootstrapService(secret_key=settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    checksum_service = Sha256ChecksumService()
    credential_service = PasswordStationCredentialService()
    realtime = request.app.state.realtime
    qr_base_url = resolve_settings_qr_base_url(settings)

    return UseCases(
        generate_bootstrap=GenerateBootstrapUseCase(
            bootstrap_service=bootstrap_service,
            clock=clock,
            base_url=qr_base_url,
            environment=settings.environment,
            protocol_version=settings.protocol_version,
            bootstrap_ttl_seconds=settings.bootstrap_token_ttl_seconds,
        ),
        validate_bootstrap=ValidateBootstrapUseCase(bootstrap_service=bootstrap_service),
        list_active_stations=ListActiveStationsUseCase(station_repository=repositories.stations),
        connect_station=ConnectStationUseCase(
            station_repository=repositories.stations,
            session_repository=repositories.sessions,
            audit_repository=repositories.audit,
            credential_service=credential_service,
            token_service=token_service,
            clock=clock,
            id_generator=id_generator,
            session_ttl_seconds=settings.operational_token_ttl_seconds,
            realtime=realtime,
        ),
        restore_session=RestoreSessionUseCase(
            session_repository=repositories.sessions,
            token_service=token_service,
            clock=clock,
        ),
        create_match=CreateMatchUseCase(
            match_repository=repositories.matches,
            session_repository=repositories.sessions,
            audit_repository=repositories.audit,
            clock=clock,
            id_generator=id_generator,
        ),
        ingest_score_event=IngestScoreEventUseCase(
            idempotency_repository=repositories.idempotency,
            session_repository=repositories.sessions,
            match_repository=repositories.matches,
            score_event_repository=repositories.score_events,
            audit_repository=repositories.audit,
            realtime=realtime,
            clock=clock,
            id_generator=id_generator,
            presentation_category_start_score=Decimal(str(settings.judge_presentation_category_start_score)),
        ),
        finalize_match=FinalizeMatchUseCase(
            finalization_repository=repositories.finalizations,
            match_repository=repositories.matches,
            score_event_repository=repositories.score_events,
            session_repository=repositories.sessions,
            station_repository=repositories.stations,
            checksum_service=checksum_service,
            audit_repository=repositories.audit,
            realtime=realtime,
            clock=clock,
            id_generator=id_generator,
            presentation_category_start_score=Decimal(str(settings.judge_presentation_category_start_score)),
        ),
        next_round=NextRoundUseCase(
            match_repository=repositories.matches,
            audit_repository=repositories.audit,
            realtime=realtime,
            clock=clock,
            id_generator=id_generator,
        ),
        reset_round=ResetRoundUseCase(
            match_repository=repositories.matches,
            score_event_repository=repositories.score_events,
            audit_repository=repositories.audit,
            realtime=realtime,
            clock=clock,
            id_generator=id_generator,
        ),
        reset_match=ResetMatchUseCase(
            match_repository=repositories.matches,
            score_event_repository=repositories.score_events,
            audit_repository=repositories.audit,
            realtime=realtime,
            clock=clock,
            id_generator=id_generator,
            finalization_repository=repositories.finalizations,
            session_repository=repositories.sessions,
        ),
        match_summary=GetMatchSummaryUseCase(
            match_repository=repositories.matches,
            score_event_repository=repositories.score_events,
            session_repository=repositories.sessions,
            finalization_repository=repositories.finalizations,
            presentation_category_start_score=Decimal(str(settings.judge_presentation_category_start_score)),
        ),
        station_active_session=GetStationActiveSessionUseCase(session_repository=repositories.sessions),
        station_active_match_state=GetStationActiveMatchStateUseCase(
            station_repository=repositories.stations,
            session_repository=repositories.sessions,
            match_repository=repositories.matches,
            clock=clock,
            lookup_limit=settings.match_query_limit_active_lookup,
        ),
    )


def get_admin_use_cases(
    request: Request,
    settings: Settings = Depends(get_settings),
    repositories: Repositories = Depends(get_repositories),
) -> AdminUseCases:
    clock = UtcClock()
    id_generator = UuidIdGenerator()
    bootstrap_service = JwtBootstrapService(secret_key=settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    credential_service = PasswordStationCredentialService()
    credential_generator = NumericCredentialGenerator()
    qr_base_url = resolve_settings_qr_base_url(settings)

    return AdminUseCases(
        views=AdminViewUseCases(
            station_repository=repositories.stations,
            session_repository=repositories.sessions,
            match_repository=repositories.matches,
            score_event_repository=repositories.score_events,
            audit_repository=repositories.audit,
            finalization_repository=repositories.finalizations,
            bootstrap_service=bootstrap_service,
            credential_service=credential_service,
            credential_generator=credential_generator,
            clock=clock,
            id_generator=id_generator,
            base_url=qr_base_url,
            environment=settings.environment,
            tournament_id=settings.tournament_id,
            protocol_version=settings.protocol_version,
            bootstrap_ttl_seconds=settings.bootstrap_token_ttl_seconds,
            station_credential_ttl_seconds=settings.station_credential_ttl_seconds,
            station_credential_rotation_seconds=settings.station_credential_rotation_seconds,
            history_retention_matches=settings.history_retention_matches,
            judge_default_rounds=settings.judge_default_rounds,
            judge_default_starting_score=Decimal(str(settings.judge_default_starting_score)),
            judge_presentation_category_start_score=Decimal(str(settings.judge_presentation_category_start_score)),
            judge_action_value_1=Decimal(str(settings.judge_action_value_1)),
            judge_action_value_2=Decimal(str(settings.judge_action_value_2)),
            judge_official_counts=settings.judge_official_counts_values,
            match_query_limit_active_lookup=settings.match_query_limit_active_lookup,
            match_query_limit_scoreboard=settings.match_query_limit_scoreboard,
            history_delete_bulk_scan_limit=settings.history_delete_bulk_scan_limit,
            station_credential_create_length=settings.station_credential_create_length,
            station_credential_rotate_length=settings.station_credential_rotate_length,
            realtime=request.app.state.realtime,
            is_session_connected=request.app.state.connection_hub.is_session_connected,
            connected_sessions_by_station=request.app.state.connection_hub.connected_session_ids_for_station,
            credential_cipher=FernetCredentialCipher(secret_key=settings.jwt_secret_key),
        ),
        kick_judge_session=KickJudgeSessionUseCase(
            session_repository=repositories.sessions,
            station_repository=repositories.stations,
            audit_repository=repositories.audit,
            realtime=request.app.state.realtime,
            clock=clock,
            id_generator=id_generator,
            match_repository=repositories.matches,
            finalization_repository=repositories.finalizations,
            match_lookup_limit=settings.match_query_limit_active_lookup,
        ),
    )
