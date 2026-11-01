from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable

import anyio

from tkd_scorer.application.dto.admin_dto import (
    AdminActiveMatchView,
    AdminCategoryOptionView,
    AdminCompetitorResultView,
    AdminCompetitorRoundResultView,
    AdminConsolidatedResultView,
    AdminDashboardView,
    AdminDrawPoomsaesView,
    AdminHistoryView,
    AdminJudgeDeltaEventView,
    AdminJudgeFinalizationStatusView,
    AdminJudgeSubmissionView,
    AdminMatchResultView,
    AdminMatchStartView,
    AdminResultsView,
    AdminRoundConsolidatedView,
    AdminScoreboardJudgeColumnView,
    AdminScoreboardRoundView,
    AdminScoreboardRowView,
    AdminScoreboardSideView,
    AdminSessionView,
    AdminStartMatchResult,
    AdminStationDetailView,
    AdminStationLiveSnapshot,
    AdminStationRow,
    AdminStationScoreboardView,
    StationCredentialView,
)
from tkd_scorer.application.use_cases._datetime_format import to_iso_utc_z
from tkd_scorer.application.use_cases._helpers import from_json_payload, to_json_payload
from tkd_scorer.application.use_cases._match_scoring import MatchScoring, build_match_scoring
from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import (
    AthleteSide,
    MatchStatus,
    RoundStatus,
    StationStatus,
)
from tkd_scorer.domain.entities.match import Match, MatchRound
from tkd_scorer.domain.entities.station import Station
from tkd_scorer.domain.exceptions.errors import ConflictError, NotFoundError, ValidationError
from tkd_scorer.domain.services.judge_consolidation import REMATCH, ConsolidatedMatch
from tkd_scorer.domain.services.poomsae_draw import (
    category_label,
    draw_poomsaes_for_match,
    list_supported_categories,
    poomsaes_for_category,
    validate_selected_poomsaes,
)
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort
from tkd_scorer.ports.realtime.realtime_port import RealtimePort
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.finalization_repository_port import FinalizationRepositoryPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.score_event_repository_port import ScoreEventRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort
from tkd_scorer.ports.repositories.station_repository_port import StationRepositoryPort
from tkd_scorer.ports.security.credential_cipher_port import CredentialCipherPort
from tkd_scorer.ports.security.station_credential_service_port import StationCredentialServicePort
from tkd_scorer.ports.services.bootstrap_service_port import BootstrapServicePort
from tkd_scorer.ports.services.credential_generator_port import CredentialGeneratorPort


class AdminViewUseCases:
    def __init__(
        self,
        *,
        station_repository: StationRepositoryPort,
        session_repository: SessionRepositoryPort,
        match_repository: MatchRepositoryPort,
        score_event_repository: ScoreEventRepositoryPort,
        audit_repository: AuditRepositoryPort,
        bootstrap_service: BootstrapServicePort,
        credential_service: StationCredentialServicePort,
        credential_generator: CredentialGeneratorPort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
        base_url: str,
        environment: str,
        tournament_id: str,
        protocol_version: str,
        bootstrap_ttl_seconds: int,
        station_credential_ttl_seconds: int,
        station_credential_rotation_seconds: int,
        history_retention_matches: int,
        finalization_repository: FinalizationRepositoryPort | None = None,
        judge_default_rounds: int = 2,
        judge_default_starting_score: Decimal = Decimal("4.0"),
        judge_presentation_category_start_score: Decimal = Decimal("2.0"),
        judge_action_value_1: Decimal = Decimal("0.1"),
        judge_action_value_2: Decimal = Decimal("0.3"),
        judge_official_counts: set[int] | None = None,
        match_query_limit_active_lookup: int = 50,
        match_query_limit_scoreboard: int = 300,
        history_delete_bulk_scan_limit: int = 100000,
        station_credential_create_length: int = 4,
        station_credential_rotate_length: int = 6,
        realtime: RealtimePort | None = None,
        is_session_connected: Callable[[str], bool] | None = None,
        connected_sessions_by_station: Callable[[str], set[str]] | None = None,
        credential_cipher: CredentialCipherPort | None = None,
    ) -> None:
        self._credential_cipher = credential_cipher
        self._station_repository = station_repository
        self._session_repository = session_repository
        self._match_repository = match_repository
        self._score_event_repository = score_event_repository
        self._audit_repository = audit_repository
        self._bootstrap_service = bootstrap_service
        self._credential_service = credential_service
        self._credential_generator = credential_generator
        self._clock = clock
        self._id_generator = id_generator
        self._base_url = base_url
        self._environment = environment
        self._tournament_id = tournament_id
        self._protocol_version = protocol_version
        self._bootstrap_ttl_seconds = bootstrap_ttl_seconds
        self._station_credential_ttl_seconds = station_credential_ttl_seconds
        self._station_credential_rotation_seconds = station_credential_rotation_seconds
        self._history_retention_matches = history_retention_matches
        self._finalization_repository = finalization_repository
        self._judge_default_rounds = max(1, int(judge_default_rounds))
        self._judge_default_starting_score = Decimal(str(judge_default_starting_score))
        self._judge_presentation_category_start_score = Decimal(str(judge_presentation_category_start_score))
        self._judge_action_value_1 = Decimal(str(judge_action_value_1))
        self._judge_action_value_2 = Decimal(str(judge_action_value_2))
        resolved_official_counts = judge_official_counts or {3, 5, 7}
        self._judge_official_counts = {int(item) for item in resolved_official_counts if int(item) > 0} or {3, 5, 7}
        self._match_query_limit_active_lookup = max(1, int(match_query_limit_active_lookup))
        self._match_query_limit_scoreboard = max(1, int(match_query_limit_scoreboard))
        self._history_delete_bulk_scan_limit = max(1, int(history_delete_bulk_scan_limit))
        self._station_credential_create_length = max(1, int(station_credential_create_length))
        self._station_credential_rotate_length = max(1, int(station_credential_rotate_length))
        self._realtime = realtime
        self._is_session_connected = is_session_connected
        self._connected_sessions_by_station = connected_sessions_by_station

    def dashboard(self) -> AdminDashboardView:
        stations = self._station_repository.list_all()
        station_rows: list[AdminStationRow] = []
        for station in stations:
            active_sessions = self._session_repository.list_active_by_station(station.id)
            connected_sessions = self._filter_connected_sessions(station.id, active_sessions)
            session = connected_sessions[0] if connected_sessions else active_sessions[0] if active_sessions else None
            judge_names = list(dict.fromkeys(item.judge_name for item in connected_sessions if item.judge_name.strip()))
            active_session_ids = [item.id for item in active_sessions]
            connected_judge_names = list(
                dict.fromkeys(item.judge_name for item in connected_sessions if item.judge_name.strip())
            )
            judge_label = (
                f"{session.judge_name} +{len(connected_sessions) - 1}"
                if session and len(connected_sessions) > 1
                else session.judge_name
                if session
                else None
            )
            station_rows.append(
                AdminStationRow(
                    station_id=station.id,
                    station_name=station.name,
                    status=station.status.value,
                    active_session_id=session.id if session else None,
                    judge_name=judge_label,
                    device_id=session.device_id if session else None,
                    active_sessions_count=len(active_sessions),
                    judge_names=judge_names,
                    active_session_ids=active_session_ids,
                    connected_sessions_count=len(connected_sessions),
                    connected_judge_names=connected_judge_names,
                )
            )

        active_matches = self._match_repository.list_recent(
            limit=200,
            statuses=[MatchStatus.IN_PROGRESS.value, MatchStatus.FINALIZATION_PENDING.value],
        )
        recent_matches = self._match_repository.list_recent(limit=20)
        return AdminDashboardView(
            generated_at=self._clock.now(),
            total_stations=len(station_rows),
            occupied_stations=len([item for item in station_rows if item.status == StationStatus.OCCUPIED.value]),
            active_sessions=sum(item.connected_sessions_count for item in station_rows),
            active_matches=len(active_matches),
            recent_matches=len(recent_matches),
            stations=station_rows,
        )

    def stations(self) -> list[AdminStationRow]:
        stations = self._station_repository.list_all()
        rows: list[AdminStationRow] = []
        for station in stations:
            active_sessions = self._session_repository.list_active_by_station(station.id)
            connected_sessions = self._filter_connected_sessions(station.id, active_sessions)
            session = connected_sessions[0] if connected_sessions else active_sessions[0] if active_sessions else None
            judge_names = list(dict.fromkeys(item.judge_name for item in connected_sessions if item.judge_name.strip()))
            active_session_ids = [item.id for item in active_sessions]
            connected_judge_names = list(
                dict.fromkeys(item.judge_name for item in connected_sessions if item.judge_name.strip())
            )
            judge_label = (
                f"{session.judge_name} +{len(connected_sessions) - 1}"
                if session and len(connected_sessions) > 1
                else session.judge_name
                if session
                else None
            )
            rows.append(
                AdminStationRow(
                    station_id=station.id,
                    station_name=station.name,
                    status=station.status.value,
                    active_session_id=session.id if session else None,
                    judge_name=judge_label,
                    device_id=session.device_id if session else None,
                    active_sessions_count=len(active_sessions),
                    judge_names=judge_names,
                    active_session_ids=active_session_ids,
                    connected_sessions_count=len(connected_sessions),
                    connected_judge_names=connected_judge_names,
                )
            )
        return rows

    def create_station(
        self,
        *,
        station_name: str,
        station_id: str | None,
        expected_judge_name: str | None,
        credential: str | None,
        actor: str,
    ) -> AdminStationRow:
        name = station_name.strip()
        if not name:
            raise ValidationError("stationName is required")

        resolved_station_id = self._resolve_station_id(name=name, value=station_id)
        if self._station_repository.get_by_id(resolved_station_id) is not None:
            raise ConflictError("Station ID already exists")

        plain_credential = (
            credential.strip()
            if credential and credential.strip()
            else self._credential_generator.generate(length=self._station_credential_create_length)
        )
        now = self._clock.now()

        station = Station(
            id=resolved_station_id,
            name=name,
            status=StationStatus.ACTIVE,
            credential_hash=self._credential_service.hash_credential(plain_credential),
            credential_encrypted=self._encrypt_credential(plain_credential),
            credential_expires_at=now + timedelta(seconds=self._station_credential_ttl_seconds),
            expected_judge_name=expected_judge_name.strip() if expected_judge_name and expected_judge_name.strip() else None,
            active_session_id=None,
            updated_at=now,
        )
        self._station_repository.save(station)

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="station",
                action="create",
                subject_id=station.id,
                actor=actor,
                details=f"name={station.name}",
                occurred_at=now,
            )
        )

        return AdminStationRow(
            station_id=station.id,
            station_name=station.name,
            status=station.status.value,
            active_session_id=None,
            judge_name=None,
            device_id=None,
            active_sessions_count=0,
            judge_names=[],
            active_session_ids=[],
            connected_sessions_count=0,
            connected_judge_names=[],
        )

    def delete_station(self, station_id: str, *, actor: str) -> None:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")

        active_sessions = self._session_repository.list_active_by_station(station_id)
        if active_sessions:
            raise ConflictError("Cannot delete occupied station")

        active_match = self._find_station_active_match(station_id)
        if active_match is not None:
            raise ConflictError("Cannot delete station with active match")

        deleted = self._station_repository.delete(station_id)
        if not deleted:
            raise ConflictError("Cannot delete station with historical records")

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="station",
                action="delete",
                subject_id=station_id,
                actor=actor,
                details=f"name={station.name}",
                occurred_at=self._clock.now(),
            )
        )

    def station_detail(self, station_id: str, *, reveal_credential: bool) -> AdminStationDetailView:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")

        sessions = self._session_repository.list_active_by_station(station_id)
        connected_session_ids = self._connected_session_ids(station_id)
        connected_sessions = [item for item in sessions if item.id in connected_session_ids]
        session = connected_sessions[0] if connected_sessions else sessions[0] if sessions else None
        active_session = (
            AdminSessionView(
                session_id=session.id,
                judge_name=session.judge_name,
                device_id=session.device_id,
                status=session.status.value,
                expires_at=session.expires_at,
                is_connected=session.id in connected_session_ids,
            )
            if session
            else None
        )
        active_sessions = [
            AdminSessionView(
                session_id=item.id,
                judge_name=item.judge_name,
                device_id=item.device_id,
                status=item.status.value,
                expires_at=item.expires_at,
                is_connected=item.id in connected_session_ids,
            )
            for item in sessions
        ]

        live_snapshot = self.station_live_snapshot(
            station_id=station_id,
            rotate_credential=False,
            actor="admin-view",
            reveal_credential=reveal_credential,
        )

        active_match = self._find_station_active_match(station_id)
        current_match = self._build_match_result(active_match) if active_match else None

        return AdminStationDetailView(
            station_id=station.id,
            station_name=station.name,
            status=station.status.value,
            active_session=active_session,
            active_sessions=active_sessions,
            credential_masked=live_snapshot.credential_masked,
            credential_revealed=live_snapshot.credential_revealed,
            credential_expires_at=live_snapshot.credential_expires_at,
            bootstrap_payload_json=live_snapshot.bootstrap_payload_json,
            current_match=current_match,
        )

    def match_detail(self, match_id: str) -> AdminMatchResultView:
        match = self._match_repository.get_match(match_id)
        if match is None:
            raise NotFoundError("Match not found")
        return self._build_match_result(match)

    def results(self) -> AdminResultsView:
        matches = self._match_repository.list_recent(
            limit=self._history_retention_matches,
            statuses=[MatchStatus.FINISHED.value, MatchStatus.FINALIZATION_PENDING.value],
        )
        return AdminResultsView(
            generated_at=self._clock.now(),
            results=[self._build_match_result(item) for item in matches],
        )

    def history(self) -> AdminHistoryView:
        matches = self._match_repository.list_recent(limit=self._history_retention_matches)
        return AdminHistoryView(
            generated_at=self._clock.now(),
            matches=[self._build_match_result(item) for item in matches],
        )

    def delete_history_match(self, *, match_id: str, actor: str) -> None:
        match = self._match_repository.get_match(match_id)
        if match is None:
            raise NotFoundError("Match not found")
        if self._is_protected_active_match(match):
            raise ConflictError("Cannot delete a match that is active or pending reconciliation")

        deleted = self._match_repository.delete_match(match_id)
        if not deleted:
            raise NotFoundError("Match not found")

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="history",
                action="delete_match",
                subject_id=match_id,
                actor=actor,
                details=to_json_payload(
                    {
                        "matchId": match_id,
                        "stationId": match.station_id,
                        "judgeName": match.judge_name,
                        "status": match.status.value,
                    }
                ),
                occurred_at=self._clock.now(),
            )
        )

    def delete_all_history_matches(self, *, actor: str) -> tuple[int, int]:
        matches = self._match_repository.list_recent(limit=self._history_delete_bulk_scan_limit)
        deleted = 0
        skipped_active = 0

        for match in matches:
            if self._is_protected_active_match(match):
                skipped_active += 1
                continue
            if self._match_repository.delete_match(match.id):
                deleted += 1

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="history",
                action="delete_all",
                subject_id="all",
                actor=actor,
                details=to_json_payload(
                    {
                        "deleted": deleted,
                        "skippedActive": skipped_active,
                    }
                ),
                occurred_at=self._clock.now(),
            )
        )
        return deleted, skipped_active

    def _is_protected_active_match(self, match: Match) -> bool:
        return match.is_live(self._session_repository.list_active_by_station(match.station_id))

    def start_match(
        self,
        *,
        station_id: str,
        competitor_left_name: str,
        competitor_right_name: str,
        category_id: str,
        selected_poomsaes: list[str],
        total_rounds: int,
        actor: str,
        drawn_poomsaes: list[str] | None = None,
    ) -> AdminStartMatchResult:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")

        active_match = self._find_station_active_match(station_id)
        if active_match is not None:
            raise ConflictError("This station already has an active match")

        active_sessions = sorted(
            self._session_repository.list_active_by_station(station_id),
            key=lambda item: self._as_utc(item.created_at),
        )
        session = active_sessions[0] if active_sessions else None
        if session is None:
            raise ConflictError("An active judge session is required to start the match")

        left_name = competitor_left_name.strip()
        right_name = competitor_right_name.strip()
        if not left_name:
            raise ValidationError("Red competitor name is required")
        if not right_name:
            raise ValidationError("Blue competitor name is required")
        if total_rounds <= 0:
            raise ValidationError("totalRounds must be greater than zero")

        resolved_category_id = category_id.strip().lower()
        resolved_category_label = category_label(resolved_category_id)
        cleaned_selected_poomsaes = validate_selected_poomsaes(
            resolved_category_id,
            selected_poomsaes,
        )
        resolved_drawn_poomsaes = self._resolve_drawn_poomsaes(
            category_id=resolved_category_id,
            selected_poomsaes=cleaned_selected_poomsaes,
            total_rounds=total_rounds,
            drawn_poomsaes=drawn_poomsaes,
        )

        now = self._clock.now()
        # One shared match per fight: every judge of the station scores it with its own session and the
        # match closes once all of them (the active sessions now) have finalized.
        match = Match(
            id=self._id_generator.new("match"),
            station_id=station_id,
            session_id=session.id,
            judge_name=session.judge_name,
            competitor_left_name=left_name,
            competitor_right_name=right_name,
            total_rounds=total_rounds,
            current_round=1,
            starting_score=self._judge_default_starting_score,
            status=MatchStatus.PENDING,
            created_at=now,
        )
        match.set_judges(item.scorecard_key for item in active_sessions)
        match.start(now)
        self._match_repository.save_match(match)
        self._match_repository.upsert_round(
            MatchRound(
                id=self._id_generator.new("round"),
                match_id=match.id,
                round_number=1,
                status=RoundStatus.ACTIVE,
                started_at=now,
            )
        )

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="create",
                subject_id=match.id,
                actor=session.judge_name,
                details=f"station_id={station_id}",
                occurred_at=now,
            )
        )
        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="start",
                subject_id=match.id,
                actor=actor,
                details=to_json_payload(
                    {
                        "stationId": station_id,
                        "categoryId": resolved_category_id,
                        "categoryLabel": resolved_category_label,
                        "selectedPoomsaes": cleaned_selected_poomsaes,
                        "drawnPoomsaes": resolved_drawn_poomsaes,
                        "judgesRequired": match.judges_required,
                        "judgeSessionIds": [item.id for item in active_sessions],
                    }
                ),
                occurred_at=now,
            )
        )
        self._clear_station_pending_draw(station_id=station_id, actor=actor)
        self._publish_match_started_event(
            station_id=station_id,
            match_id=match.id,
            competitor_left_name=left_name,
            competitor_right_name=right_name,
            total_rounds=total_rounds,
            current_round=match.current_round,
            category_id=resolved_category_id,
            category_label=resolved_category_label,
            drawn_poomsaes=resolved_drawn_poomsaes,
            started_at=now,
        )

        return AdminStartMatchResult(
            match_id=match.id,
            station_id=station_id,
            category_id=resolved_category_id,
            category_label=resolved_category_label,
            drawn_poomsaes=resolved_drawn_poomsaes,
        )

    def draw_match_poomsaes(
        self,
        *,
        category_id: str,
        selected_poomsaes: list[str],
        total_rounds: int,
    ) -> AdminDrawPoomsaesView:
        resolved_category_id = category_id.strip().lower()
        resolved_category_label = category_label(resolved_category_id)
        cleaned_selected_poomsaes = validate_selected_poomsaes(
            resolved_category_id,
            selected_poomsaes,
        )
        resolved_drawn_poomsaes = draw_poomsaes_for_match(
            category_id=resolved_category_id,
            selected_poomsaes=cleaned_selected_poomsaes,
            total_rounds=total_rounds,
        )
        return AdminDrawPoomsaesView(
            category_id=resolved_category_id,
            category_label=resolved_category_label,
            total_rounds=total_rounds,
            drawn_poomsaes=resolved_drawn_poomsaes,
        )

    def draw_station_match_poomsaes(
        self,
        *,
        station_id: str,
        category_id: str,
        selected_poomsaes: list[str],
        total_rounds: int,
        actor: str,
        competitor_left_name: str | None = None,
        competitor_right_name: str | None = None,
    ) -> AdminDrawPoomsaesView:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")

        left_name = competitor_left_name.strip() if competitor_left_name and competitor_left_name.strip() else None
        right_name = competitor_right_name.strip() if competitor_right_name and competitor_right_name.strip() else None

        preview = self.draw_match_poomsaes(
            category_id=category_id,
            selected_poomsaes=selected_poomsaes,
            total_rounds=total_rounds,
        )

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="draw_preview",
                subject_id=station_id,
                actor=actor,
                details=to_json_payload(
                    {
                        "stationId": station_id,
                        "categoryId": preview.category_id,
                        "categoryLabel": preview.category_label,
                        "totalRounds": preview.total_rounds,
                        "drawnPoomsaes": preview.drawn_poomsaes,
                        "competitorLeftName": left_name,
                        "competitorRightName": right_name,
                    }
                ),
                occurred_at=self._clock.now(),
            )
        )
        return preview

    def save_station_match_competitors(
        self,
        *,
        station_id: str,
        competitor_left_name: str,
        competitor_right_name: str,
        actor: str,
    ) -> None:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")

        left_name = competitor_left_name.strip()
        right_name = competitor_right_name.strip()
        if not left_name:
            raise ValidationError("Red competitor name is required")
        if not right_name:
            raise ValidationError("Blue competitor name is required")

        existing_preview = self._read_station_pending_draw(station_id=station_id)
        details = dict(existing_preview) if isinstance(existing_preview, dict) else {}
        details.update(
            {
                "stationId": station_id,
                "competitorLeftName": left_name,
                "competitorRightName": right_name,
            }
        )

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="draw_preview",
                subject_id=station_id,
                actor=actor,
                details=to_json_payload(details),
                occurred_at=self._clock.now(),
            )
        )

    def active_match(self, station_id: str) -> AdminActiveMatchView | None:
        active_match = self._find_station_active_match(station_id)
        if active_match is None:
            return None

        match_metadata = self._read_match_metadata(match_id=active_match.id)
        timer_state = self._resolve_round_timer_state(active_match)
        primary_action, primary_label_key = self._resolve_round_primary_action(
            current_round=active_match.current_round,
            total_rounds=active_match.total_rounds,
            timer_status=timer_state["status"],
        )
        timer_reference_started_at = None
        if timer_state["status"] == "running":
            reference = self._clock.now() - timedelta(seconds=int(timer_state["elapsed_seconds"]))
            timer_reference_started_at = to_iso_utc_z(reference)
        return AdminActiveMatchView(
            station_id=station_id,
            match_id=active_match.id,
            competitor_left_name=active_match.competitor_left_name,
            competitor_right_name=active_match.competitor_right_name,
            current_round=active_match.current_round,
            total_rounds=active_match.total_rounds,
            category_label=self._as_string(match_metadata.get("categoryLabel")),
            drawn_poomsaes=self._as_string_list(match_metadata.get("drawnPoomsaes")),
            timer_status=timer_state["status"],
            elapsed_seconds=timer_state["elapsed_seconds"],
            elapsed_label=self._format_elapsed_seconds(timer_state["elapsed_seconds"]),
            timer_reference_started_at=timer_reference_started_at,
            primary_action=primary_action,
            primary_label_key=primary_label_key,
            can_pause_timer=timer_state["status"] == "running",
            can_reset_round=True,
            can_finalize_match=True,
        )

    def start_active_round(self, *, station_id: str, actor: str) -> None:
        match = self._require_station_active_match(station_id)
        timer_state = self._resolve_round_timer_state(match)
        status = timer_state["status"]
        if status == "running":
            raise ValidationError("The round is already running")
        if status == "completed":
            raise ValidationError("The match has already completed all rounds")

        now = self._clock.now()
        current_round = self._match_repository.get_round(match.id, match.current_round)
        if current_round is None:
            current_round = MatchRound(
                id=self._id_generator.new("round"),
                match_id=match.id,
                round_number=match.current_round,
                status=RoundStatus.PENDING,
            )
        current_round.status = RoundStatus.ACTIVE
        if status != "paused":
            current_round.started_at = now
            current_round.ended_at = None
            elapsed_seconds = 0
        else:
            elapsed_seconds = timer_state["elapsed_seconds"]
        self._match_repository.upsert_round(current_round)

        self._save_round_timer_state(
            match_id=match.id,
            actor=actor,
            status="running",
            round_number=match.current_round,
            elapsed_seconds=elapsed_seconds,
            last_started_at=now,
        )

    def pause_active_round_timer(self, *, station_id: str, actor: str) -> None:
        match = self._require_station_active_match(station_id)
        timer_state = self._resolve_round_timer_state(match)
        if timer_state["status"] != "running":
            raise ValidationError("The timer can only be paused while the round is running")

        self._save_round_timer_state(
            match_id=match.id,
            actor=actor,
            status="paused",
            round_number=match.current_round,
            elapsed_seconds=timer_state["elapsed_seconds"],
            last_started_at=None,
        )

    def stop_active_round(self, *, station_id: str, actor: str) -> None:
        match = self._require_station_active_match(station_id)
        timer_state = self._resolve_round_timer_state(match)
        if timer_state["status"] not in ("running", "paused"):
            raise ValidationError("The round must be started before it can be stopped")

        now = self._clock.now()
        current_round = self._match_repository.get_round(match.id, match.current_round)
        if current_round is None:
            current_round = MatchRound(
                id=self._id_generator.new("round"),
                match_id=match.id,
                round_number=match.current_round,
                status=RoundStatus.ACTIVE,
            )
        current_round.status = RoundStatus.FINISHED
        if current_round.started_at is None:
            current_round.started_at = now
        current_round.ended_at = now
        self._match_repository.upsert_round(current_round)

        elapsed_seconds = timer_state["elapsed_seconds"]
        if match.current_round < match.total_rounds:
            next_round_number = match.next_round()
            self._match_repository.save_match(match)
            next_round = self._match_repository.get_round(match.id, next_round_number)
            if next_round is None:
                next_round = MatchRound(
                    id=self._id_generator.new("round"),
                    match_id=match.id,
                    round_number=next_round_number,
                    status=RoundStatus.PENDING,
                )
            else:
                next_round.status = RoundStatus.PENDING
                next_round.started_at = None
                next_round.ended_at = None
            self._match_repository.upsert_round(next_round)
            self._save_round_timer_state(
                match_id=match.id,
                actor=actor,
                status="idle",
                round_number=next_round_number,
                elapsed_seconds=0,
                last_started_at=None,
            )
        else:
            self._save_round_timer_state(
                match_id=match.id,
                actor=actor,
                status="completed",
                round_number=match.current_round,
                elapsed_seconds=elapsed_seconds,
                last_started_at=None,
            )

    def reset_active_round(self, *, station_id: str, actor: str) -> None:
        match = self._require_station_active_match(station_id)
        current_round = self._match_repository.get_round(match.id, match.current_round)
        if current_round is None:
            current_round = MatchRound(
                id=self._id_generator.new("round"),
                match_id=match.id,
                round_number=match.current_round,
                status=RoundStatus.PENDING,
            )

        self._score_event_repository.delete_for_match_round(match.id, match.current_round)
        current_round.status = RoundStatus.PENDING
        current_round.started_at = None
        current_round.ended_at = None
        self._match_repository.upsert_round(current_round)

        self._save_round_timer_state(
            match_id=match.id,
            actor=actor,
            status="idle",
            round_number=match.current_round,
            elapsed_seconds=0,
            last_started_at=None,
        )
        # The judges' phones keep their own copy of the events: tell them to delete the same round,
        # otherwise their scorecards no longer match the server and their finalizations do not reconcile.
        self._publish_to_station(
            "reset_round",
            station_id=station_id,
            payload={"matchId": match.id, "round": match.current_round},
        )

    def finalize_active_match(self, *, station_id: str, actor: str) -> None:
        match = self._require_station_active_match(station_id)
        timer_state = self._resolve_round_timer_state(match)

        now = self._clock.now()
        current_round = self._match_repository.get_round(match.id, match.current_round)
        if current_round is None:
            current_round = MatchRound(
                id=self._id_generator.new("round"),
                match_id=match.id,
                round_number=match.current_round,
                status=RoundStatus.FINISHED,
                started_at=now,
                ended_at=now,
            )
        elif current_round.status != RoundStatus.FINISHED:
            if current_round.started_at is None:
                current_round.started_at = now
            current_round.finish(now)
        self._match_repository.upsert_round(current_round)

        match.finish(now)
        self._match_repository.save_match(match)

        self._save_round_timer_state(
            match_id=match.id,
            actor=actor,
            status="completed",
            round_number=match.current_round,
            elapsed_seconds=timer_state["elapsed_seconds"],
            last_started_at=None,
        )
        self._publish_active_match_state(
            station_id=station_id,
            has_active_match=False,
            issued_at=now,
            match_id=match.id,
        )
        self._publish_to_station(
            "match_updated",
            station_id=station_id,
            payload={
                "matchId": match.id,
                "status": match.status.value,
            },
        )

    def station_scoreboard(self, station_id: str) -> AdminStationScoreboardView:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")
        pending_draw = self._read_station_pending_draw(station_id=station_id)
        pending_competitor_left_name = self._as_string(pending_draw.get("competitorLeftName"))
        pending_competitor_right_name = self._as_string(pending_draw.get("competitorRightName"))

        active_sessions = self._session_repository.list_active_by_station(station_id)
        connected_session_ids = self._connected_session_ids(station_id)
        connected_sessions = self._filter_connected_sessions(station_id, active_sessions)
        connected_judges = [
            AdminSessionView(
                session_id=item.id,
                judge_name=item.judge_name,
                device_id=item.device_id,
                status=item.status.value,
                expires_at=item.expires_at,
                is_connected=True,
            )
            for item in connected_sessions
        ]
        connected_judges_count = self._connected_judges_count(station_id)

        start_view = self._build_start_view()
        reference_match = self._find_station_active_match(station_id)
        display_match = reference_match
        if display_match is None and not (pending_competitor_left_name or pending_competitor_right_name):
            display_match = self._latest_closed_station_match(station_id)

        if display_match is not None:
            resolved_judges_required = max(1, display_match.judges_required)
        elif connected_judges_count > 0:
            resolved_judges_required = connected_judges_count
        else:
            resolved_judges_required = 3
        if display_match is None and connected_judges_count == 0:
            scoring_mode_valid = True
            scoring_mode_label_key = "scoring_mode.default"
        else:
            scoring_mode_valid = resolved_judges_required in self._judge_official_counts
            scoring_mode_label_key = "scoring_mode.official" if scoring_mode_valid else "scoring_mode.test"

        competitor_left_name: str | None = None
        competitor_right_name: str | None = None
        current_red_score: Decimal | None = None
        current_blue_score: Decimal | None = None
        current_status: str | None = None
        current_round: int | None = None
        total_rounds: int | None = None
        current_match_id: str | None = None
        match_category_id: str | None = None
        match_category_label: str | None = None
        match_poomsaes: list[str] = []
        submissions: list[AdminJudgeSubmissionView] = []
        round_consolidated: list[AdminRoundConsolidatedView] = []
        judge_finalization: list[AdminJudgeFinalizationStatusView] = []
        judge_delta_events: list[AdminJudgeDeltaEventView] = []
        judge_columns: list[AdminScoreboardJudgeColumnView] = []
        side_scorecards: list[AdminScoreboardSideView] = []
        consolidated = AdminConsolidatedResultView(
            judges_required=resolved_judges_required,
            judges_finalized=0,
            all_finalized=False,
            red_score=None,
            blue_score=None,
            winner_side=None,
            winner_label_key=None,
        )

        if display_match is not None:
            current_match_id = display_match.id
            competitor_left_name = display_match.competitor_left_name
            competitor_right_name = display_match.competitor_right_name
            current_status = display_match.status.value
            current_round = display_match.current_round
            total_rounds = display_match.total_rounds
            match_metadata = self._read_match_metadata(match_id=display_match.id)
            match_category_id = self._as_string(match_metadata.get("categoryId"))
            match_category_label = self._as_string(match_metadata.get("categoryLabel"))
            match_poomsaes = self._as_string_list(match_metadata.get("drawnPoomsaes"))

            scoring = self._match_scoring(
                display_match,
                station_sessions=active_sessions if reference_match is not None else (),
            )
            judge_columns = [
                AdminScoreboardJudgeColumnView(
                    alias=item.alias,
                    session_id=item.session_id,
                    judge_name=item.judge_name,
                    connected=_judge_connected(item.session_ids, connected_session_ids),
                    finalized=item.finalized,
                    reconciled=item.reconciled,
                    removed=item.removed,
                )
                for item in scoring.judges
            ]
            judge_finalization = [
                AdminJudgeFinalizationStatusView(
                    judge_name=item.judge_name,
                    finalized=item.finalized,
                    alias=item.alias,
                    connected=_judge_connected(item.session_ids, connected_session_ids),
                    reconciled=item.reconciled,
                    removed=item.removed,
                )
                for item in scoring.judges
            ]
            submissions = [
                AdminJudgeSubmissionView(
                    judge_name=item.judge_name,
                    match_id=display_match.id,
                    status=item.finalization.status,
                    red_score=item.scorecard.final_score_red,
                    blue_score=item.scorecard.final_score_blue,
                    finalized_at=item.finalization.created_at,
                    alias=item.alias,
                    reconciled=item.reconciled,
                    session_id=item.session_id,
                )
                for item in scoring.judges
                if item.finalization is not None
            ]
            aliases = {session_id: item.alias for item in scoring.judges for session_id in item.session_ids}
            judge_delta_events = sorted(
                (
                    AdminJudgeDeltaEventView(
                        judge_name=event.judge_name,
                        sequence=event.sequence,
                        round_number=event.round_number,
                        athlete_side=event.athlete_side.value,
                        score_delta=event.score_delta,
                        occurred_at=event.occurred_at,
                        alias=aliases.get(event.session_id, ""),
                        score_target=event.score_target.value,
                        score_after=event.score_after,
                    )
                    for event in scoring.events
                ),
                key=lambda item: (item.occurred_at, item.sequence),
                reverse=True,
            )

            displayed = scoring.result
            current_red_score = displayed.score_red
            current_blue_score = displayed.score_blue
            side_scorecards = self._build_side_scorecards(
                scoring=scoring,
                displayed=displayed,
                competitor_left_name=competitor_left_name,
                competitor_right_name=competitor_right_name,
                poomsaes=match_poomsaes,
            )
            round_consolidated = [
                AdminRoundConsolidatedView(
                    round_number=item.round_number,
                    red_score=item.score_red,
                    blue_score=item.score_blue,
                )
                for item in displayed.rounds
            ]

            official = scoring.final if scoring.all_finalized or display_match.status != MatchStatus.IN_PROGRESS else None
            winner = official.winner if official is not None else None
            consolidated = AdminConsolidatedResultView(
                judges_required=scoring.judges_required,
                judges_finalized=scoring.judges_finalized,
                all_finalized=official is not None,
                red_score=official.score_red if official is not None else None,
                blue_score=official.score_blue if official is not None else None,
                winner_side=winner,
                winner_label_key=self._winner_label_key(winner),
            )
        else:
            match_category_id = self._as_string(pending_draw.get("categoryId"))
            match_category_label = self._as_string(pending_draw.get("categoryLabel"))
            match_poomsaes = self._as_string_list(pending_draw.get("drawnPoomsaes"))
            competitor_left_name = self._as_string(pending_draw.get("competitorLeftName"))
            competitor_right_name = self._as_string(pending_draw.get("competitorRightName"))
            total_rounds_value = pending_draw.get("totalRounds")
            if isinstance(total_rounds_value, int) and total_rounds_value > 0:
                total_rounds = total_rounds_value
            for index, session in enumerate(sorted(connected_sessions, key=lambda item: self._as_utc(item.created_at))):
                alias = f"J{index + 1}"
                judge_columns.append(
                    AdminScoreboardJudgeColumnView(
                        alias=alias,
                        session_id=session.id,
                        judge_name=session.judge_name,
                        connected=True,
                        finalized=False,
                        reconciled=False,
                    )
                )
                judge_finalization.append(
                    AdminJudgeFinalizationStatusView(
                        judge_name=session.judge_name,
                        finalized=False,
                        alias=alias,
                        connected=True,
                    )
                )

        resolved_default_category_id = self._resolve_station_default_category_id(
            station_id=station_id,
            current_category_id=match_category_id,
        )
        match_category_id = resolved_default_category_id
        match_category_label = category_label(resolved_default_category_id)

        return AdminStationScoreboardView(
            station_id=station.id,
            station_name=station.name,
            generated_at=self._clock.now(),
            judges_required=resolved_judges_required,
            connected_judges_count=connected_judges_count,
            connected_judges=connected_judges,
            scoring_mode_valid=scoring_mode_valid,
            scoring_mode_label_key=scoring_mode_label_key,
            has_active_match=reference_match is not None,
            match_category_id=match_category_id,
            match_category_label=match_category_label,
            match_poomsaes=match_poomsaes,
            competitor_left_name=competitor_left_name,
            competitor_right_name=competitor_right_name,
            current_red_score=current_red_score,
            current_blue_score=current_blue_score,
            current_match_status=current_status,
            current_round=current_round,
            total_rounds=total_rounds,
            judge_submissions=submissions,
            judge_finalization=judge_finalization,
            round_consolidated=round_consolidated,
            consolidated=consolidated,
            start_view=start_view,
            pending_competitor_left_name=pending_competitor_left_name,
            pending_competitor_right_name=pending_competitor_right_name,
            judge_delta_events=judge_delta_events,
            current_match_id=current_match_id,
            judge_columns=judge_columns,
            side_scorecards=side_scorecards,
            showing_closed_match=reference_match is None and display_match is not None,
        )

    @staticmethod
    def _build_side_scorecards(
        *,
        scoring: MatchScoring,
        displayed: ConsolidatedMatch,
        competitor_left_name: str | None,
        competitor_right_name: str | None,
        poomsaes: list[str],
    ) -> list[AdminScoreboardSideView]:
        round_numbers = sorted(
            {item.round_number for item in displayed.rounds}
            | {item.round_number for judge in scoring.judges for item in judge.scorecard.rounds}
        )
        sides: list[AdminScoreboardSideView] = []
        for side, name in ((AthleteSide.RED, competitor_left_name), (AthleteSide.BLUE, competitor_right_name)):
            rounds: list[AdminScoreboardRoundView] = []
            for round_number in round_numbers:
                judge_rounds = [judge.scorecard.round(round_number) for judge in scoring.judges]
                consolidated_round = displayed.round(round_number)
                rounds.append(
                    AdminScoreboardRoundView(
                        round_number=round_number,
                        poomsae=poomsaes[round_number - 1] if len(poomsaes) >= round_number else None,
                        technique=AdminScoreboardRowView(
                            judge_values=[item.technique(side) if item else None for item in judge_rounds],
                            consolidated=consolidated_round.technique(side) if consolidated_round else None,
                        ),
                        presentation=AdminScoreboardRowView(
                            judge_values=[item.presentation(side) if item else None for item in judge_rounds],
                            consolidated=consolidated_round.presentation(side) if consolidated_round else None,
                        ),
                        round_score=consolidated_round.score(side) if consolidated_round else None,
                    )
                )
            sides.append(
                AdminScoreboardSideView(
                    side=side.value,
                    competitor_name=name,
                    rounds=rounds,
                    total=displayed.score(side),
                )
            )
        return sides

    @staticmethod
    def _winner_label_key(winner: str | None) -> str | None:
        if winner == "red":
            return "winner.red"
        if winner == "blue":
            return "winner.blue"
        if winner == REMATCH:
            return "winner.rematch"
        if winner == "draw":
            return "winner.tie"
        return None

    def _latest_closed_station_match(self, station_id: str) -> Match | None:
        """Last match of the station when it is closed (finished or pending reconciliation), for the result screen."""
        for match in self._match_repository.list_recent(limit=self._match_query_limit_scoreboard):
            if match.station_id != station_id:
                continue
            if match.status in (MatchStatus.FINISHED, MatchStatus.FINALIZATION_PENDING):
                return match
            return None
        return None

    def _match_scoring(self, match: Match, *, station_sessions=()) -> MatchScoring:
        return build_match_scoring(
            match=match,
            score_event_repository=self._score_event_repository,
            session_repository=self._session_repository,
            finalization_repository=self._finalization_repository,
            presentation_category_start=self._judge_presentation_category_start_score,
            station_sessions=station_sessions,
        )

    def get_station_credential(self, station_id: str, *, reveal: bool) -> StationCredentialView:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")

        plain = self._decrypt_credential(station.credential_encrypted)
        if plain is None:
            # Stored with another server key (TKD_JWT_SECRET_KEY changed): the panel asks to rotate it.
            return StationCredentialView(
                station_id=station_id,
                masked="",
                revealed=None,
                expires_at=station.credential_expires_at,
                unreadable=True,
            )
        masked = self._mask_credential(plain)
        return StationCredentialView(
            station_id=station_id,
            masked=masked,
            revealed=plain if reveal and plain else None,
            expires_at=station.credential_expires_at,
        )

    def _encrypt_credential(self, plain: str) -> str | None:
        if self._credential_cipher is None:
            return None
        return self._credential_cipher.encrypt(plain)

    def _decrypt_credential(self, encrypted: str | None) -> str | None:
        """Plain PIN; "" when none is stored; None when the stored value cannot be decrypted."""
        if not encrypted or self._credential_cipher is None:
            return ""
        return self._credential_cipher.decrypt(encrypted)

    def rotate_station_credential(self, station_id: str, *, actor: str) -> StationCredentialView:
        return self._rotate_station_credential_internal(station_id=station_id, actor=actor, audit=True)

    def station_live_snapshot(
        self,
        *,
        station_id: str,
        rotate_credential: bool,
        actor: str,
        reveal_credential: bool,
    ) -> AdminStationLiveSnapshot:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")
        if rotate_credential:
            now = self._as_utc(self._clock.now())
            updated_at = self._as_utc(station.updated_at) if station.updated_at is not None else None
            should_rotate = updated_at is None or (
                (now - updated_at).total_seconds() >= self._station_credential_rotation_seconds
            )
            if should_rotate:
                self._rotate_station_credential_internal(station_id=station_id, actor=actor, audit=False)
                station = self._station_repository.get_by_id(station_id)
                if station is None:
                    raise NotFoundError("Station not found")

        credential_view = self.get_station_credential(station_id, reveal=reveal_credential)
        expires_at = self._clock.now() + timedelta(seconds=self._bootstrap_ttl_seconds)
        bootstrap_token = self._bootstrap_service.issue_bootstrap_token(
            tournament_id=self._tournament_id,
            expires_at=expires_at,
        )
        bootstrap_payload = {
            "baseUrl": self._base_url,
            "stationId": station_id,
            "stationName": station.name,
            "bootstrapToken": bootstrap_token,
            "environment": self._environment,
            "tournamentId": self._tournament_id,
            "protocolVersion": self._protocol_version,
            "expiresAt": to_iso_utc_z(expires_at),
        }
        return AdminStationLiveSnapshot(
            station_id=station_id,
            station_name=station.name,
            credential_masked=credential_view.masked,
            credential_revealed=credential_view.revealed,
            credential_expires_at=credential_view.expires_at,
            bootstrap_payload_json=json.dumps(bootstrap_payload),
            credential_unreadable=credential_view.unreadable,
        )

    def _build_match_result(self, match: Match) -> AdminMatchResultView:
        scoring = self._match_scoring(match)
        result = scoring.result
        result_views: list[AdminCompetitorResultView] = []
        for side, name in (
            (AthleteSide.RED, match.competitor_left_name),
            (AthleteSide.BLUE, match.competitor_right_name),
        ):
            round_one = result.round(1)
            round_two = result.round(2)
            result_views.append(
                AdminCompetitorResultView(
                    side=side.value,
                    competitor_name=name,
                    poomsae_1=round_one.score(side) if round_one else None,
                    poomsae_2=round_two.score(side) if round_two else None,
                    tec_score=result.technique_average(side),
                    pres_score=result.presentation_average(side),
                    final_score=result.score(side),
                    rounds=[
                        AdminCompetitorRoundResultView(
                            round_number=item.round_number,
                            tec_score=item.technique(side),
                            pres_score=item.presentation(side),
                            score=item.score(side),
                        )
                        for item in result.rounds
                    ],
                )
            )

        notes = (
            "match_detail.reconciliation_pending"
            if match.status == MatchStatus.FINALIZATION_PENDING
            else None
        )
        return AdminMatchResultView(
            match_id=match.id,
            station_id=match.station_id,
            judge_name=match.judge_name,
            status=match.status.value,
            current_round=match.current_round,
            total_rounds=match.total_rounds,
            competitor_results=result_views,
            finalization_notes_key=notes,
            judge_names=[f"{item.alias} {item.judge_name}" for item in scoring.judges],
            judges_finalized=scoring.judges_finalized,
            judges_required=scoring.judges_required,
            winner_side=scoring.final.winner if scoring.final is not None else None,
        )

    def _find_station_active_match(self, station_id: str) -> Match | None:
        matches = self._match_repository.list_recent(
            limit=self._match_query_limit_active_lookup,
            statuses=[MatchStatus.IN_PROGRESS.value, MatchStatus.FINALIZATION_PENDING.value],
        )
        active_sessions = self._session_repository.list_active_by_station(station_id)
        for match in matches:
            if match.station_id == station_id and match.is_live(active_sessions):
                return match
        return None

    def _require_station_active_match(self, station_id: str) -> Match:
        match = self._find_station_active_match(station_id)
        if match is None:
            raise NotFoundError("This station has no active match")
        return match

    def _resolve_round_timer_state(self, match: Match) -> dict[str, int | str | datetime | None]:
        now = self._clock.now()
        state = {
            "status": "idle",
            "round_number": match.current_round,
            "elapsed_seconds": 0,
            "last_started_at": None,
        }
        events = self._audit_repository.list_recent(
            limit=1,
            category="match",
            action="round_timer_state",
            subject_id=match.id,
        )
        if not events:
            return state

        details = self._safe_json_dict(events[0].details)
        status = self._as_string(details.get("status")) or "idle"
        elapsed = details.get("elapsedSeconds")
        round_number = details.get("roundNumber")
        last_started_at = self._as_datetime_utc(details.get("lastStartedAt"))

        if status not in ("idle", "running", "paused", "completed"):
            status = "idle"
        elapsed_seconds = elapsed if isinstance(elapsed, int) and elapsed >= 0 else 0
        resolved_round_number = (
            round_number
            if isinstance(round_number, int) and round_number > 0
            else match.current_round
        )
        if resolved_round_number != match.current_round and status != "completed":
            status = "idle"
            resolved_round_number = match.current_round
            elapsed_seconds = 0
            last_started_at = None

        if status == "running" and last_started_at is not None:
            elapsed_seconds += max(0, int((now - last_started_at).total_seconds()))

        return {
            "status": status,
            "round_number": resolved_round_number,
            "elapsed_seconds": elapsed_seconds,
            "last_started_at": last_started_at,
        }

    def _save_round_timer_state(
        self,
        *,
        match_id: str,
        actor: str,
        status: str,
        round_number: int,
        elapsed_seconds: int,
        last_started_at: datetime | None,
    ) -> None:
        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="round_timer_state",
                subject_id=match_id,
                actor=actor,
                details=to_json_payload(
                    {
                        "status": status,
                        "roundNumber": round_number,
                        "elapsedSeconds": max(0, int(elapsed_seconds)),
                        "lastStartedAt": to_iso_utc_z(last_started_at) if last_started_at else None,
                    }
                ),
                occurred_at=self._clock.now(),
            )
        )

    @staticmethod
    def _resolve_round_primary_action(
        *,
        current_round: int,
        total_rounds: int,
        timer_status: str,
    ) -> tuple[str, str]:
        if timer_status == "running":
            return "stop_round", "round_action.stop"
        if timer_status == "paused":
            return "start_round", "round_action.resume"
        if timer_status == "completed" and current_round >= total_rounds:
            return "none", "round_action.completed"
        if current_round > 1:
            return "start_round", "round_action.start_another"
        return "start_round", "round_action.start"

    def _connected_judges_count(self, station_id: str) -> int:
        sessions = self._filter_connected_sessions(
            station_id,
            self._session_repository.list_active_by_station(station_id),
        )
        judges = {item.judge_name.strip().lower() for item in sessions if item.judge_name.strip()}
        return len(judges)

    def _connected_session_ids(self, station_id: str) -> set[str]:
        if self._connected_sessions_by_station is None:
            sessions = self._session_repository.list_active_by_station(station_id)
            return {item.id for item in sessions}
        try:
            return set(self._connected_sessions_by_station(station_id))
        except Exception:
            return set()

    def _is_connected_session(self, *, station_id: str, session_id: str, connected_session_ids: set[str]) -> bool:
        if session_id in connected_session_ids:
            return True
        if self._is_session_connected is None:
            return session_id in {item.id for item in self._session_repository.list_active_by_station(station_id)}
        try:
            return bool(self._is_session_connected(session_id))
        except Exception:
            return False

    def _filter_connected_sessions(self, station_id: str, sessions: list) -> list:
        connected_session_ids = self._connected_session_ids(station_id)
        return [
            item
            for item in sessions
            if self._is_connected_session(
                station_id=station_id,
                session_id=item.id,
                connected_session_ids=connected_session_ids,
            )
        ]

    @staticmethod
    def _resolve_drawn_poomsaes(
        *,
        category_id: str,
        selected_poomsaes: list[str],
        total_rounds: int,
        drawn_poomsaes: list[str] | None,
    ) -> list[str]:
        if not drawn_poomsaes:
            return draw_poomsaes_for_match(
                category_id=category_id,
                selected_poomsaes=selected_poomsaes,
                total_rounds=total_rounds,
            )

        provided = [item.strip() for item in drawn_poomsaes if item and item.strip()]
        if len(provided) != total_rounds:
            raise ValidationError("The draw does not match the number of rounds")
        if len(set(provided)) != len(provided):
            raise ValidationError("The draw contains duplicate poomsaes")

        allowed = set(selected_poomsaes)
        if any(item not in allowed for item in provided):
            raise ValidationError("The draw does not match the selected poomsaes")
        return provided

    def _read_match_metadata(self, *, match_id: str) -> dict:
        events = self._audit_repository.list_recent(
            limit=1,
            category="match",
            action="start",
            subject_id=match_id,
        )
        if not events:
            return {}
        try:
            return from_json_payload(events[0].details)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _read_station_pending_draw(self, *, station_id: str) -> dict:
        events = self._audit_repository.list_recent(
            limit=1,
            category="match",
            action="draw_preview",
            subject_id=station_id,
        )
        if not events:
            return {}
        try:
            return from_json_payload(events[0].details)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _clear_station_pending_draw(self, *, station_id: str, actor: str) -> None:
        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="draw_preview",
                subject_id=station_id,
                actor=actor,
                details=to_json_payload({"stationId": station_id}),
                occurred_at=self._clock.now(),
            )
        )

    def _publish_match_started_event(
        self,
        *,
        station_id: str,
        match_id: str,
        competitor_left_name: str,
        competitor_right_name: str,
        total_rounds: int,
        current_round: int,
        category_id: str,
        category_label: str,
        drawn_poomsaes: list[str],
        started_at: datetime,
    ) -> None:
        if self._realtime is None:
            return

        competitors_payload = {
            "matchId": match_id,
            "stationId": station_id,
            "competitorRedName": competitor_left_name,
            "competitorBlueName": competitor_right_name,
            "competitorLeftName": competitor_left_name,
            "competitorRightName": competitor_right_name,
            "totalRounds": total_rounds,
            "currentRound": current_round,
            "categoryId": category_id,
            "categoryLabel": category_label,
            "drawnPoomsaes": drawn_poomsaes,
            "startedAt": to_iso_utc_z(started_at),
        }

        self._publish_to_station("new_competitors", station_id=station_id, payload=competitors_payload)
        self._publish_to_station("match_updated", station_id=station_id, payload=competitors_payload)
        self._publish_active_match_state(
            station_id=station_id,
            has_active_match=True,
            issued_at=started_at,
            match_id=match_id,
            competitor_red_name=competitor_left_name,
            competitor_blue_name=competitor_right_name,
        )
        self._publish_to_station(
            "judge_settings_updated",
            station_id=station_id,
            payload=self._judge_settings_payload(issued_at=started_at),
        )

    def _publish_active_match_state(
        self,
        *,
        station_id: str,
        has_active_match: bool,
        issued_at: datetime,
        match_id: str | None = None,
        competitor_red_name: str | None = None,
        competitor_blue_name: str | None = None,
    ) -> None:
        payload = {
            "hasActiveMatch": has_active_match,
            "matchId": match_id,
            "competitorRedName": competitor_red_name,
            "competitorBlueName": competitor_blue_name,
            "issuedAt": to_iso_utc_z(issued_at),
        }
        self._publish_to_station("active_match_state", station_id=station_id, payload=payload)

    def _judge_settings_payload(self, *, issued_at: datetime) -> dict:
        return {
            "defaultRounds": self._judge_default_rounds,
            "defaultStartingScore": float(self._judge_default_starting_score),
            "presentationCategoryStartScore": float(self._judge_presentation_category_start_score),
            "actionValue1": float(self._judge_action_value_1),
            "actionValue2": float(self._judge_action_value_2),
            "issuedAt": to_iso_utc_z(issued_at),
        }

    def _publish_to_station(self, event_type: str, *, station_id: str, payload: dict) -> None:
        if self._realtime is None:
            return

        try:
            anyio.from_thread.run(
                self._realtime.publish_to_station,
                station_id,
                event_type,
                payload,
            )
            return
        except RuntimeError:
            pass

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._realtime.publish_to_station(station_id, event_type, payload))
            return

        loop.create_task(self._realtime.publish_to_station(station_id, event_type, payload))

    def _resolve_station_default_category_id(
        self,
        *,
        station_id: str,
        current_category_id: str | None,
    ) -> str:
        supported = set(list_supported_categories())

        if current_category_id and current_category_id.strip():
            candidate = current_category_id.strip().lower()
            return candidate if candidate in supported else "beginners"

        latest_draw = self._latest_draw_preview_category(station_id=station_id)
        latest_start = self._latest_started_match_category(station_id=station_id)

        if latest_draw and latest_start:
            if latest_draw[0] >= latest_start[0]:
                return latest_draw[1]
            return latest_start[1]
        if latest_draw:
            return latest_draw[1] if latest_draw[1] in supported else "beginners"
        if latest_start:
            return latest_start[1] if latest_start[1] in supported else "beginners"
        return "beginners"

    def _latest_draw_preview_category(self, *, station_id: str) -> tuple[datetime, str] | None:
        events = self._audit_repository.list_recent(
            limit=1,
            category="match",
            action="draw_preview",
            subject_id=station_id,
        )
        if not events:
            return None

        details = self._safe_json_dict(events[0].details)
        category_id = self._as_string(details.get("categoryId"))
        if not category_id:
            return None
        return events[0].occurred_at, category_id.strip().lower()

    def _latest_started_match_category(self, *, station_id: str) -> tuple[datetime, str] | None:
        events = self._audit_repository.list_recent(
            limit=200,
            category="match",
            action="start",
        )
        for event in events:
            details = self._safe_json_dict(event.details)
            details_station_id = self._as_string(details.get("stationId"))
            category_id = self._as_string(details.get("categoryId"))
            if details_station_id != station_id or not category_id:
                continue
            return event.occurred_at, category_id.strip().lower()
        return None

    @staticmethod
    def _safe_json_dict(payload: str) -> dict:
        try:
            value = from_json_payload(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _build_start_view(self) -> AdminMatchStartView:
        categories = [
            AdminCategoryOptionView(
                category_id=category_id,
                category_label=category_label(category_id),
                poomsaes=list(poomsaes_for_category(category_id)),
            )
            for category_id in list_supported_categories()
        ]
        return AdminMatchStartView(categories=categories)

    @staticmethod
    def _as_string(value: object) -> str | None:
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _as_int(*values: object) -> int | None:
        for value in values:
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    return int(value.strip())
                except ValueError:
                    continue
        return None

    @staticmethod
    def _as_decimal(*values: object) -> Decimal | None:
        for value in values:
            if value is None:
                continue
            try:
                return Decimal(str(value)).quantize(Decimal("0.1"))
            except (InvalidOperation, ValueError):
                continue
        return None

    @staticmethod
    def _as_string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str) and item.strip()]

    @staticmethod
    def _as_datetime_utc(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        raw = value.strip()
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _format_elapsed_seconds(total_seconds: int) -> str:
        seconds = max(0, int(total_seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        rem_seconds = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{rem_seconds:02d}"

    @staticmethod
    def _mask_credential(plain: str) -> str:
        if not plain:
            return "(not set)"
        if len(plain) <= 2:
            return "*" * len(plain)
        return f"{plain[0]}{'*' * (len(plain) - 2)}{plain[-1]}"

    def _rotate_station_credential_internal(
        self,
        *,
        station_id: str,
        actor: str,
        audit: bool,
    ) -> StationCredentialView:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")

        plain = self._credential_generator.generate(length=self._station_credential_rotate_length)
        now = self._clock.now()
        station.credential_hash = self._credential_service.hash_credential(plain)
        station.credential_encrypted = self._encrypt_credential(plain)
        station.credential_expires_at = now + timedelta(seconds=self._station_credential_ttl_seconds)
        station.updated_at = now
        self._station_repository.save(station)

        if audit:
            self._audit_repository.save(
                AuditEvent(
                    id=self._id_generator.new("audit"),
                    category="station",
                    action="rotate_credential",
                    subject_id=station.id,
                    actor=actor,
                    details="credential rotated",
                    occurred_at=now,
                )
            )

        return StationCredentialView(
            station_id=station_id,
            masked=self._mask_credential(plain),
            revealed=plain,
            expires_at=station.credential_expires_at,
        )

    def _resolve_station_id(self, *, name: str, value: str | None) -> str:
        if value and value.strip():
            candidate = value.strip().lower()
        else:
            candidate = name.strip().lower()

        normalized = re.sub(r"[^a-z0-9]+", "-", candidate).strip("-")
        if not normalized:
            normalized = f"station-{self._id_generator.new('id')[-6:]}"
        return normalized

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _judge_connected(session_ids: tuple[str, ...], connected_session_ids: set[str]) -> bool:
    return any(item in connected_session_ids for item in session_ids)
