import html
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tkd_scorer.application.dto.admin_dto import (
    AdminActiveMatchView,
    AdminCategoryOptionView,
    AdminCompetitorResultView,
    AdminConsolidatedResultView,
    AdminDashboardView,
    AdminHistoryView,
    AdminJudgeFinalizationStatusView,
    AdminJudgeSubmissionView,
    AdminMatchResultView,
    AdminMatchStartView,
    AdminResultsView,
    AdminRoundConsolidatedView,
    AdminSessionView,
    AdminStartMatchResult,
    AdminStationDetailView,
    AdminStationLiveSnapshot,
    AdminStationRow,
    AdminStationScoreboardView,
    StationCredentialView,
)
from tkd_scorer.infra.config.settings import get_settings
from tkd_scorer.infra.fastapi.dependencies import AdminUseCases, get_admin_use_cases
from tkd_scorer.infra.i18n import load_catalog


class FakeAdminViews:
    def __init__(self) -> None:
        self.dashboard_called = 0
        self.station_detail_called = 0
        self.rotate_called = 0
        self.delete_called = 0
        self.start_match_called = 0
        self.draw_poomsaes_called = 0
        self.save_participants_called = 0
        self.start_round_called = 0
        self.stop_round_called = 0
        self.pause_round_called = 0
        self.reset_round_called = 0
        self.finalize_active_called = 0
        self.delete_history_match_called = 0
        self.delete_history_all_called = 0
        self.connected_judges_count = 3

    def dashboard(self) -> AdminDashboardView:
        self.dashboard_called += 1
        return AdminDashboardView(
            generated_at=datetime(2026, 3, 19),
            total_stations=1,
            occupied_stations=0,
            active_sessions=0,
            active_matches=0,
            recent_matches=0,
            stations=[
                AdminStationRow(
                    station_id="station-01",
                    station_name="Station 01",
                    status="active",
                    active_session_id=None,
                    judge_name=None,
                    device_id=None,
                )
            ],
        )

    def stations(self) -> list[AdminStationRow]:
        return []

    def create_station(
        self,
        *,
        station_name: str,
        station_id: str | None,
        expected_judge_name: str | None,
        credential: str | None,
        actor: str,
    ) -> AdminStationRow:
        return AdminStationRow(
            station_id=station_id or "station-01",
            station_name=station_name,
            status="active",
            active_session_id=None,
            judge_name=None,
            device_id=None,
        )

    def station_detail(self, station_id: str, *, reveal_credential: bool) -> AdminStationDetailView:
        self.station_detail_called += 1
        active_session = AdminSessionView(
            session_id="sess-1",
            judge_name="Judge 1",
            device_id="device-1",
            status="active",
            expires_at=None,
        )
        return AdminStationDetailView(
            station_id=station_id,
            station_name="Station 01",
            status="active",
            active_session=active_session,
            active_sessions=[active_session],
            credential_masked="1***4",
            credential_revealed="1234" if reveal_credential else None,
            credential_expires_at=None,
            bootstrap_payload_json='{"stationId":"station-01"}',
            current_match=AdminMatchResultView(
                match_id="match-1",
                station_id="station-01",
                judge_name="Judge 1",
                status="in_progress",
                current_round=1,
                total_rounds=2,
                competitor_results=[
                    AdminCompetitorResultView(
                        side="red",
                        competitor_name="Competitor A",
                        poomsae_1=Decimal("9.7"),
                        poomsae_2=Decimal("9.8"),
                        tec_score=Decimal("5.88"),
                        pres_score=Decimal("3.92"),
                        final_score=Decimal("9.80"),
                    )
                ],
                finalization_notes_key=None,
            ),
        )

    def station_live_snapshot(
        self,
        *,
        station_id: str,
        rotate_credential: bool,
        actor: str,
        reveal_credential: bool,
    ) -> AdminStationLiveSnapshot:
        return AdminStationLiveSnapshot(
            station_id=station_id,
            station_name="Station 01",
            credential_masked="1***4",
            credential_revealed="1234" if reveal_credential else None,
            credential_expires_at=None,
            bootstrap_payload_json='{"stationId":"station-01"}',
        )

    def match_detail(self, match_id: str) -> AdminMatchResultView:
        return self.station_detail("station-01", reveal_credential=False).current_match

    def results(self) -> AdminResultsView:
        return AdminResultsView(generated_at=datetime(2026, 3, 19), results=[])

    def history(self) -> AdminHistoryView:
        return AdminHistoryView(generated_at=datetime(2026, 3, 19), matches=[])

    def delete_history_match(self, *, match_id: str, actor: str) -> None:
        self.delete_history_match_called += 1

    def delete_all_history_matches(self, *, actor: str) -> tuple[int, int]:
        self.delete_history_all_called += 1
        return (3, 0)

    def get_station_credential(self, station_id: str, *, reveal: bool) -> StationCredentialView:
        return StationCredentialView(station_id=station_id, masked="1***4", revealed="1234", expires_at=None)

    def rotate_station_credential(self, station_id: str, *, actor: str) -> StationCredentialView:
        self.rotate_called += 1
        return StationCredentialView(station_id=station_id, masked="6****2", revealed="654322", expires_at=None)

    def delete_station(self, station_id: str, *, actor: str) -> None:
        self.delete_called += 1

    def station_scoreboard(self, station_id: str) -> AdminStationScoreboardView:
        judges_required = self.connected_judges_count if self.connected_judges_count > 0 else 3
        scoring_mode_valid = judges_required in (3, 5, 7)
        scoring_mode_label_key = "scoring_mode.official" if scoring_mode_valid else "scoring_mode.test"
        return AdminStationScoreboardView(
            station_id=station_id,
            station_name="Station 01",
            generated_at=datetime(2026, 3, 19),
            judges_required=judges_required,
            connected_judges_count=judges_required,
            connected_judges=[
                AdminSessionView(
                    session_id="sess-1",
                    judge_name="Judge 1",
                    device_id="device-1",
                    status="active",
                    expires_at=None,
                )
            ],
            scoring_mode_valid=scoring_mode_valid,
            scoring_mode_label_key=scoring_mode_label_key,
            has_active_match=True,
            match_category_id="advanced",
            match_category_label="Advanced",
            match_poomsaes=["Taeguk 6", "Taeguk 8"],
            competitor_left_name="Competitor A",
            competitor_right_name="Competitor B",
            current_red_score=Decimal("9.80"),
            current_blue_score=Decimal("9.70"),
            current_match_status="in_progress",
            current_round=2,
            total_rounds=2,
            judge_submissions=[
                AdminJudgeSubmissionView(
                    judge_name="Judge 1",
                    match_id="match-1",
                    status="finished",
                    red_score=Decimal("9.80"),
                    blue_score=Decimal("9.70"),
                    finalized_at=None,
                )
            ],
            judge_finalization=[
                AdminJudgeFinalizationStatusView(judge_name="Judge 1", finalized=True),
            ],
            round_consolidated=[
                AdminRoundConsolidatedView(
                    round_number=1,
                    red_score=Decimal("9.8"),
                    blue_score=Decimal("9.7"),
                ),
                AdminRoundConsolidatedView(
                    round_number=2,
                    red_score=Decimal("9.8"),
                    blue_score=Decimal("9.7"),
                ),
            ],
            consolidated=AdminConsolidatedResultView(
                judges_required=judges_required,
                judges_finalized=1,
                all_finalized=False,
                red_score=None,
                blue_score=None,
                winner_side=None,
                winner_label_key=None,
            ),
            start_view=AdminMatchStartView(
                categories=[
                    AdminCategoryOptionView(
                        category_id="advanced",
                        category_label="Advanced",
                        poomsaes=["Taeguk 5", "Taeguk 6", "Taeguk 7", "Taeguk 8"],
                    )
                ]
            ),
        )

    def active_match(self, station_id: str) -> AdminActiveMatchView | None:
        return AdminActiveMatchView(
            station_id=station_id,
            match_id="match-1",
            competitor_left_name="Competitor A",
            competitor_right_name="Competitor B",
            current_round=1,
            total_rounds=2,
            category_label="Advanced",
            drawn_poomsaes=["Taeguk 6", "Taeguk 8"],
            timer_status="idle",
            elapsed_seconds=0,
            elapsed_label="00:00:00",
            timer_reference_started_at=None,
            primary_action="start_round",
            primary_label_key="round_action.start",
            can_pause_timer=False,
            can_reset_round=True,
            can_finalize_match=False,
        )

    def start_match(
        self,
        *,
        station_id: str,
        competitor_left_name: str,
        competitor_right_name: str,
        category_id: str,
        selected_poomsaes: list[str],
        drawn_poomsaes: list[str] | None = None,
        total_rounds: int,
        actor: str,
    ) -> AdminStartMatchResult:
        self.start_match_called += 1
        effective_draw = drawn_poomsaes or selected_poomsaes[:total_rounds]
        return AdminStartMatchResult(
            match_id="match-started",
            station_id=station_id,
            category_id=category_id,
            category_label="Advanced",
            drawn_poomsaes=effective_draw,
        )

    def draw_match_poomsaes(
        self,
        *,
        category_id: str,
        selected_poomsaes: list[str],
        total_rounds: int,
    ):
        self.draw_poomsaes_called += 1

        class _Preview:
            def __init__(self, category: str, poomsaes: list[str]) -> None:
                self.category_id = category
                self.category_label = "Advanced"
                self.total_rounds = total_rounds
                self.drawn_poomsaes = poomsaes[:total_rounds]

        return _Preview(category_id, selected_poomsaes)

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
    ):
        return self.draw_match_poomsaes(
            category_id=category_id,
            selected_poomsaes=selected_poomsaes,
            total_rounds=total_rounds,
        )

    def save_station_match_competitors(
        self,
        *,
        station_id: str,
        competitor_left_name: str,
        competitor_right_name: str,
        actor: str,
    ) -> None:
        self.save_participants_called += 1

    def start_active_round(self, *, station_id: str, actor: str) -> None:
        self.start_round_called += 1

    def stop_active_round(self, *, station_id: str, actor: str) -> None:
        self.stop_round_called += 1

    def pause_active_round_timer(self, *, station_id: str, actor: str) -> None:
        self.pause_round_called += 1

    def reset_active_round(self, *, station_id: str, actor: str) -> None:
        self.reset_round_called += 1

    def finalize_active_match(self, *, station_id: str, actor: str) -> None:
        self.finalize_active_called += 1


class FakeKickJudgeSessionUseCase:
    def __init__(self) -> None:
        self.called = 0

    async def execute(self, *, station_id: str, session_id: str, reason: str, actor: str) -> None:
        self.called += 1


def _client(
    tmp_path: Path,
    *,
    admin_password: str = "",
    admin_base_path: str = "/admin",
    admin_ip_allowlist: str = "",
    admin_login_max_attempts: int = 5,
    admin_login_window_seconds: int = 300,
    admin_login_lockout_seconds: int = 300,
    admin_security_fail_fast: bool = False,
    admin_trust_proxy_headers: bool = False,
    ui_language: str = "en",
) -> TestClient:
    db_path = tmp_path / "admin_test.db"
    get_settings.cache_clear()

    from os import environ

    environ["TKD_DATABASE_URL"] = f"sqlite:///{db_path}"
    environ["TKD_JWT_SECRET_KEY"] = "test-jwt-secret"
    environ["TKD_ADMIN_PASSWORD"] = admin_password
    environ["TKD_ADMIN_BASE_PATH"] = admin_base_path
    environ["TKD_ADMIN_IP_ALLOWLIST"] = admin_ip_allowlist
    environ["TKD_ADMIN_LOGIN_MAX_ATTEMPTS"] = str(admin_login_max_attempts)
    environ["TKD_ADMIN_LOGIN_WINDOW_SECONDS"] = str(admin_login_window_seconds)
    environ["TKD_ADMIN_LOGIN_LOCKOUT_SECONDS"] = str(admin_login_lockout_seconds)
    environ["TKD_ADMIN_SECURITY_FAIL_FAST"] = "true" if admin_security_fail_fast else "false"
    environ["TKD_ADMIN_TRUST_PROXY_HEADERS"] = "true" if admin_trust_proxy_headers else "false"
    environ["TKD_UI_LANGUAGE"] = ui_language
    from tkd_scorer.infra.fastapi.admin_auth import reset_admin_auth_state_for_tests

    reset_admin_auth_state_for_tests()
    from tkd_scorer.entry_points.fastapi.app import create_app

    app = create_app()
    return TestClient(app)


def test_admin_dashboard_and_station_pages_render(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        dashboard = client.get("/admin")
        assert dashboard.status_code == 200
        assert "TKD Poomsae Local Administration" in dashboard.text

        stations = client.get("/admin/stations")
        assert stations.status_code == 200
        assert "Active stations" in stations.text

        detail = client.get("/admin/stations/station-01")
        assert detail.status_code == 200
        assert "Station administration" in detail.text

        scoreboard = client.get("/admin/stations/station-01/scoreboard")
        assert scoreboard.status_code == 200
        assert "TKD Poomsae Local Administration" not in scoreboard.text
        assert "Match admin" not in scoreboard.text
        assert "Back to station" not in scoreboard.text
        assert "Judges status" in scoreboard.text
        # The per-round breakdown now lives in each side card (per-judge TEC / PRES grid).
        assert 'data-side="red"' in scoreboard.text
        assert 'data-side="blue"' in scoreboard.text
        assert "Red consolidated" not in scoreboard.text

        scoreboard_debug = client.get("/admin/stations/station-01/scoreboard/debug")
        assert scoreboard_debug.status_code == 200
        assert "Live debug scoreboard" in scoreboard_debug.text
        assert "Judges consolidation" in scoreboard_debug.text

        active_match = client.get("/admin/stations/station-01/active-match")
        assert active_match.status_code == 200
        assert "No active match" in active_match.text

        match_admin = client.get("/admin/stations/station-01/match-admin")
        assert match_admin.status_code == 200
        assert "Start match" in match_admin.text
        assert "Competitor setup" in match_admin.text
        assert "Poomsae draw" in match_admin.text
        assert "Show other poomsaes" in match_admin.text
        assert "Beginners" in match_admin.text

        deleted = client.post(
            "/admin/stations/station-01/delete",
            data={"actor": "test"},
            follow_redirects=False,
        )
        assert deleted.status_code == 303
        assert deleted.headers["location"] == "/admin"

        stations_after_delete = client.get("/admin/stations")
        assert stations_after_delete.status_code == 200
        assert 'href="/admin/stations/station-01"' not in stations_after_delete.text


def test_save_competitors_persists_names_in_admin_station_form(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        saved = client.post(
            "/admin/stations/station-01/matches/save-competitors",
            data={
                "competitor_left_name": "Competitor A",
                "competitor_right_name": "Competitor B",
                "actor": "local-admin",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303

        detail = client.get("/admin/stations/station-01")
        assert detail.status_code == 200
        assert 'name="competitor_left_name"' in detail.text
        assert 'value="Competitor A"' in detail.text
        assert 'name="competitor_right_name"' in detail.text
        assert 'value="Competitor B"' in detail.text


def test_admin_routes_call_admin_use_cases_via_dependency_override(tmp_path: Path) -> None:
    fake_views = FakeAdminViews()
    fake_kick = FakeKickJudgeSessionUseCase()
    with _client(tmp_path) as client:
        app = client.app
        app.dependency_overrides[get_admin_use_cases] = lambda: AdminUseCases(
            views=fake_views,
            kick_judge_session=fake_kick,
        )

        dashboard = client.get("/admin")
        assert dashboard.status_code == 200
        assert fake_views.dashboard_called == 1

        detail = client.get("/admin/stations/station-01?reveal=1")
        assert detail.status_code == 200
        assert fake_views.station_detail_called == 1
        assert "Status: Active" in detail.text
        assert "Status: active" not in detail.text

        live_panel = client.get("/admin/stations/station-01/live-panel?auto_rotate=1")
        assert live_panel.status_code == 200

        scoreboard = client.get("/admin/stations/station-01/scoreboard")
        assert scoreboard.status_code == 200
        assert "Round timer" in scoreboard.text

        fake_views.connected_judges_count = 4
        scoreboard_non_official = client.get("/admin/stations/station-01/scoreboard")
        assert scoreboard_non_official.status_code == 200
        assert "Warning: 4 judges (test mode)" in scoreboard_non_official.text
        assert "Official consolidation only applies with 3, 5 or 7 connected judges." not in scoreboard_non_official.text

        scoreboard_debug = client.get("/admin/stations/station-01/scoreboard/debug")
        assert scoreboard_debug.status_code == 200
        assert "Round timer" in scoreboard_debug.text
        assert "Deltas received per judge" in scoreboard_debug.text

        scoreboard_debug_non_official = client.get("/admin/stations/station-01/scoreboard/debug")
        assert scoreboard_debug_non_official.status_code == 200
        assert "Warning: 4 judges (test mode)" in scoreboard_debug_non_official.text
        assert (
            "Official consolidation only applies with 3, 5 or 7 connected judges."
            not in scoreboard_debug_non_official.text
        )

        match_admin = client.get("/admin/stations/station-01/match-admin")
        assert match_admin.status_code == 200

        scoreboard_live = client.get("/admin/stations/station-01/scoreboard/live")
        assert scoreboard_live.status_code == 200

        scoreboard_debug_live = client.get("/admin/stations/station-01/scoreboard/debug/live")
        assert scoreboard_debug_live.status_code == 200

        active_panel = client.get("/admin/stations/station-01/active-match/panel")
        assert active_panel.status_code == 200

        start = client.post(
            "/admin/stations/station-01/matches/start",
            data={
                "competitor_left_name": "Competitor A",
                "competitor_right_name": "Competitor B",
                "category_id": "advanced",
                "selected_poomsaes": ["Taeguk 5", "Taeguk 6"],
                "total_rounds": 2,
                "judges_required": 3,
                "actor": "local-admin",
            },
            follow_redirects=False,
        )
        assert start.status_code == 303
        assert fake_views.start_match_called == 1

        draw = client.post(
            "/admin/stations/station-01/matches/draw",
            data={
                "competitor_left_name": "Competitor A",
                "competitor_right_name": "Competitor B",
                "category_id": "advanced",
                "selected_poomsaes": ["Taeguk 5", "Taeguk 6"],
                "total_rounds": 2,
                "judges_required": 3,
            },
        )
        assert draw.status_code == 200
        assert fake_views.draw_poomsaes_called == 1

        save_participants = client.post(
            "/admin/stations/station-01/matches/save-competitors",
            data={
                "competitor_left_name": "Competitor A",
                "competitor_right_name": "Competitor B",
                "judges_required": 3,
                "actor": "local-admin",
            },
            follow_redirects=False,
        )
        assert save_participants.status_code == 303
        assert fake_views.save_participants_called == 1

        start_round = client.post(
            "/admin/stations/station-01/active-match/start-round",
            data={"actor": "local-admin"},
            follow_redirects=False,
        )
        assert start_round.status_code == 303
        assert fake_views.start_round_called == 1

        pause_round = client.post(
            "/admin/stations/station-01/active-match/pause-timer",
            data={"actor": "local-admin"},
            follow_redirects=False,
        )
        assert pause_round.status_code == 303
        assert fake_views.pause_round_called == 1

        stop_round = client.post(
            "/admin/stations/station-01/active-match/stop-round",
            data={"actor": "local-admin"},
            follow_redirects=False,
        )
        assert stop_round.status_code == 303
        assert fake_views.stop_round_called == 1

        reset_round = client.post(
            "/admin/stations/station-01/active-match/reset-round",
            data={"actor": "local-admin"},
            follow_redirects=False,
        )
        assert reset_round.status_code == 303
        assert fake_views.reset_round_called == 1

        finalize_active = client.post(
            "/admin/stations/station-01/active-match/finalize",
            data={"actor": "local-admin"},
            follow_redirects=False,
        )
        assert finalize_active.status_code == 303
        assert fake_views.finalize_active_called == 1

        rotate = client.post(
            "/admin/stations/station-01/rotate-credential",
            data={"actor": "local-admin"},
            follow_redirects=False,
        )
        assert rotate.status_code == 303
        assert fake_views.rotate_called == 1

        kicked = client.post(
            "/admin/stations/station-01/sessions/sess-1/kick",
            data={"actor": "local-admin", "reason": "operator_replaced"},
            follow_redirects=False,
        )
        assert kicked.status_code == 303
        assert fake_kick.called == 1

        deleted = client.post(
            "/admin/stations/station-01/delete",
            data={"actor": "local-admin"},
            follow_redirects=False,
        )
        assert deleted.status_code == 303
        assert fake_views.delete_called == 1

        delete_history_match = client.post(
            "/admin/history/match-1/delete",
            data={"actor": "local-admin"},
            follow_redirects=False,
        )
        assert delete_history_match.status_code == 303
        assert fake_views.delete_history_match_called == 1

        delete_history_all = client.post(
            "/admin/history/delete-all",
            data={"actor": "local-admin"},
            follow_redirects=False,
        )
        assert delete_history_all.status_code == 303
        assert fake_views.delete_history_all_called == 1

        created = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station New",
                "station_id": "station-new",
                "actor": "local-admin",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303

        app.dependency_overrides.clear()


def test_draw_preview_is_visible_in_live_panel_before_start(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303

        draw_preview = client.post(
            "/admin/stations/station-01/matches/draw-preview",
            data={
                "competitor_left_name": "Competitor H",
                "competitor_right_name": "Competitor I",
                "category_id": "advanced",
                "selected_poomsaes": ["Taeguk 5", "Taeguk 6", "Taeguk 7"],
                "total_rounds": 2,
            },
        )
        assert draw_preview.status_code == 200
        payload = draw_preview.json()
        assert payload["drawnPoomsaes"]

        live_panel = client.get("/admin/stations/station-01/scoreboard/live")
        assert live_panel.status_code == 200
        assert payload["drawnPoomsaes"][0] in live_panel.text
        assert "Competitor H" in live_panel.text
        assert "Competitor I" in live_panel.text


def test_saved_competitors_are_visible_in_live_panel_before_start(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303

        saved = client.post(
            "/admin/stations/station-01/matches/save-competitors",
            data={
                "competitor_left_name": "Competitor G",
                "competitor_right_name": "Competitor J",
                "judges_required": 3,
                "actor": "local-admin",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303

        live_panel = client.get("/admin/stations/station-01/scoreboard/live")
        assert live_panel.status_code == 200
        assert "Competitor G" in live_panel.text
        assert "Competitor J" in live_panel.text


def test_admin_requires_login_when_password_is_configured(tmp_path: Path) -> None:
    with _client(tmp_path, admin_password="1234") as client:
        locked = client.get("/admin", follow_redirects=False)
        assert locked.status_code == 303
        assert locked.headers["location"].startswith("/admin/login?next=/admin")

        login_page = client.get("/admin/login")
        assert login_page.status_code == 200
        assert "Administration access" in login_page.text


def test_login_page_uses_spanish_labels_when_ui_language_is_es(tmp_path: Path) -> None:
    spanish = load_catalog("es")
    english = load_catalog("en")
    with _client(tmp_path, admin_password="1234", ui_language="es") as client:
        login_page = client.get("/admin/login")
        assert login_page.status_code == 200
        assert '<html lang="es">' in login_page.text
        assert spanish["login.heading"] in login_page.text
        assert english["login.heading"] not in login_page.text

        wrong_login = client.post(
            "/admin/login",
            data={"password": "9999", "next": "/admin"},
        )
        assert wrong_login.status_code == 401
        expected_error = spanish["login.error_invalid_password"].format(remaining=4)
        assert html.escape(expected_error, quote=False) in wrong_login.text


def test_admin_login_logout_flow_with_cookie(tmp_path: Path) -> None:
    with _client(tmp_path, admin_password="1234") as client:
        wrong_login = client.post(
            "/admin/login",
            data={"password": "9999", "next": "/admin"},
        )
        assert wrong_login.status_code == 401
        assert "Invalid password." in wrong_login.text

        ok_login = client.post(
            "/admin/login",
            data={"password": "1234", "next": "/admin"},
            follow_redirects=False,
        )
        assert ok_login.status_code == 303
        assert ok_login.headers["location"] == "/admin"
        assert "tkd_admin_auth=" in ok_login.headers.get("set-cookie", "")

        dashboard = client.get("/admin")
        assert dashboard.status_code == 200

        logout = client.post("/admin/logout", follow_redirects=False)
        assert logout.status_code == 303
        assert logout.headers["location"] == "/admin/login"

        locked_again = client.get("/admin", follow_redirects=False)
        assert locked_again.status_code == 303
        assert locked_again.headers["location"].startswith("/admin/login?next=/admin")


def test_live_screens_remain_public_when_admin_auth_is_enabled(tmp_path: Path) -> None:
    with _client(tmp_path, admin_password="1234") as client:
        login = client.post(
            "/admin/login",
            data={"password": "1234", "next": "/admin"},
            follow_redirects=False,
        )
        assert login.status_code == 303

        create_station = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            follow_redirects=False,
        )
        assert create_station.status_code == 303

        client.cookies.clear()

        scoreboard = client.get("/scoreboard/station-01")
        assert scoreboard.status_code == 200

        scoreboard_debug = client.get("/admin/stations/station-01/scoreboard/debug", follow_redirects=False)
        assert scoreboard_debug.status_code == 303
        assert scoreboard_debug.headers["location"].startswith("/admin/login?next=/admin/stations/station-01/scoreboard/debug")

        admin_locked = client.get("/admin/stations/station-01", follow_redirects=False)
        assert admin_locked.status_code == 303
        assert admin_locked.headers["location"].startswith("/admin/login?next=/admin/stations/station-01")


def test_admin_custom_base_path_hides_legacy_admin_path(tmp_path: Path) -> None:
    custom_base = "/secret-tkd-panel"
    with _client(tmp_path, admin_password="1234", admin_base_path=custom_base) as client:
        legacy_admin = client.get("/admin", follow_redirects=False)
        assert legacy_admin.status_code == 404

        login_page = client.get(f"{custom_base}/login")
        assert login_page.status_code == 200
        assert "Administration access" in login_page.text

        login_ok = client.post(
            f"{custom_base}/login",
            data={"password": "1234", "next": custom_base},
            follow_redirects=False,
        )
        assert login_ok.status_code == 303
        assert login_ok.headers["location"] == custom_base

        dashboard = client.get(custom_base)
        assert dashboard.status_code == 200


def test_admin_ip_allowlist_blocks_non_allowed_ips_but_keeps_live_public(tmp_path: Path) -> None:
    with _client(
        tmp_path,
        admin_password="1234",
        admin_ip_allowlist="127.0.0.1,::1",
        admin_trust_proxy_headers=True,
    ) as client:
        blocked_login = client.get("/admin/login", headers={"x-forwarded-for": "10.10.10.99"})
        assert blocked_login.status_code == 403

        login_ok = client.post(
            "/admin/login",
            data={"password": "1234", "next": "/admin"},
            headers={"x-forwarded-for": "127.0.0.1"},
            follow_redirects=False,
        )
        assert login_ok.status_code == 303

        created = client.post(
            "/admin/stations/create",
            data={
                "station_name": "Station 01",
                "station_id": "station-01",
                "credential": "1234",
                "actor": "test",
            },
            headers={"x-forwarded-for": "127.0.0.1"},
            follow_redirects=False,
        )
        assert created.status_code == 303
        client.cookies.clear()

        live_allowed = client.get(
            "/scoreboard/station-01",
            headers={"x-forwarded-for": "10.10.10.99"},
        )
        assert live_allowed.status_code == 200

        detail_blocked = client.get(
            "/admin/stations/station-01",
            headers={"x-forwarded-for": "10.10.10.99"},
            follow_redirects=False,
        )
        assert detail_blocked.status_code == 403


def test_admin_login_lockout_after_failed_attempts(tmp_path: Path) -> None:
    with _client(
        tmp_path,
        admin_password="1234",
        admin_login_max_attempts=2,
        admin_login_window_seconds=60,
        admin_login_lockout_seconds=120,
    ) as client:
        wrong_1 = client.post(
            "/admin/login",
            data={"password": "0000", "next": "/admin"},
        )
        assert wrong_1.status_code == 401
        assert "Remaining attempts: 1." in wrong_1.text

        wrong_2 = client.post(
            "/admin/login",
            data={"password": "0000", "next": "/admin"},
        )
        assert wrong_2.status_code == 429
        assert "Too many failed attempts." in wrong_2.text

        still_locked = client.post(
            "/admin/login",
            data={"password": "1234", "next": "/admin"},
        )
        assert still_locked.status_code == 429
        assert "Access temporarily locked." in still_locked.text


def test_admin_fail_fast_rejects_insecure_configuration(tmp_path: Path) -> None:
    client = _client(tmp_path, admin_security_fail_fast=True)
    with pytest.raises(RuntimeError):
        with client:
            client.get("/health")


def test_admin_fail_fast_allows_secure_configuration(tmp_path: Path) -> None:
    with _client(
        tmp_path,
        admin_password="1234567890-secure",
        admin_base_path="/secure-panel",
        admin_ip_allowlist="127.0.0.1",
        admin_security_fail_fast=True,
        admin_trust_proxy_headers=True,
    ) as client:
        login = client.get("/secure-panel/login", headers={"x-forwarded-for": "127.0.0.1"})
        assert login.status_code == 200
