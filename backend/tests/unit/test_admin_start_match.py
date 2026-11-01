from datetime import datetime

import pytest

from tests.unit.fakes import FixedClock
from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import RealtimeRecorderAdapter
from tkd_scorer.application.use_cases.admin_view_use_cases import AdminViewUseCases
from tkd_scorer.domain.entities.common import SessionStatus
from tkd_scorer.domain.exceptions.errors import ConflictError


class _BootstrapStub:
    def issue_bootstrap_token(self, *, tournament_id: str, expires_at: datetime) -> str:
        return f"bootstrap::{tournament_id}"

    def validate_bootstrap_token(self, token: str) -> dict[str, str]:
        return {"token": token}


class _CredentialGeneratorStub:
    def generate(self, *, length: int = 6) -> str:
        return "9" * length


def _use_case(fixture_bundle) -> AdminViewUseCases:
    return AdminViewUseCases(
        station_repository=fixture_bundle["stations"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        bootstrap_service=_BootstrapStub(),
        credential_service=fixture_bundle["credential_service"],
        credential_generator=_CredentialGeneratorStub(),
        clock=FixedClock(),
        id_generator=fixture_bundle["ids"],
        base_url="http://127.0.0.1:8080",
        environment="test",
        tournament_id="tkd-test",
        protocol_version="v1",
        bootstrap_ttl_seconds=180,
        station_credential_ttl_seconds=3600,
        station_credential_rotation_seconds=20,
        history_retention_matches=10,
    )


def test_start_match_creates_active_match_and_stores_draw_metadata(fixture_bundle) -> None:
    fixture_bundle["matches"].matches.clear()
    fixture_bundle["matches"].rounds.clear()
    use_case = _use_case(fixture_bundle)

    result = use_case.start_match(
        station_id="station-01",
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        category_id="advanced",
        selected_poomsaes=["Taeguk 5", "Taeguk 6", "Taeguk 7"],
        total_rounds=2,
        actor="admin",
    )

    created = fixture_bundle["matches"].get_match(result.match_id)
    assert created is not None
    assert created.competitor_left_name == "Competitor A"
    assert created.competitor_right_name == "Competitor B"

    scoreboard = use_case.station_scoreboard("station-01")
    assert scoreboard.has_active_match is True
    assert scoreboard.match_category_id == "advanced"
    assert scoreboard.match_category_label == "Advanced"
    assert len(scoreboard.match_poomsaes) == 2


def test_start_match_requires_active_session(fixture_bundle) -> None:
    fixture_bundle["matches"].matches.clear()
    fixture_bundle["matches"].rounds.clear()
    fixture_bundle["sessions"].items["sess-1"].status = SessionStatus.REVOKED
    use_case = _use_case(fixture_bundle)

    with pytest.raises(ConflictError):
        use_case.start_match(
            station_id="station-01",
            competitor_left_name="Competitor A",
            competitor_right_name="Competitor B",
            category_id="advanced",
            selected_poomsaes=["Taeguk 5", "Taeguk 6"],
            total_rounds=2,
            actor="admin",
        )


def test_start_match_uses_provided_drawn_poomsaes_when_valid(fixture_bundle) -> None:
    fixture_bundle["matches"].matches.clear()
    fixture_bundle["matches"].rounds.clear()
    use_case = _use_case(fixture_bundle)

    result = use_case.start_match(
        station_id="station-01",
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        category_id="advanced",
        selected_poomsaes=["Taeguk 5", "Taeguk 6", "Taeguk 7"],
        drawn_poomsaes=["Taeguk 7", "Taeguk 5"],
        total_rounds=2,
        actor="admin",
    )

    assert result.drawn_poomsaes == ["Taeguk 7", "Taeguk 5"]


def test_draw_match_poomsaes_returns_preview(fixture_bundle) -> None:
    use_case = _use_case(fixture_bundle)

    preview = use_case.draw_match_poomsaes(
        category_id="advanced",
        selected_poomsaes=["Taeguk 5", "Taeguk 6", "Taeguk 7"],
        total_rounds=2,
    )

    assert preview.category_id == "advanced"
    assert preview.category_label == "Advanced"
    assert len(preview.drawn_poomsaes) == 2


def test_station_scoreboard_shows_drawn_poomsaes_before_starting_match(fixture_bundle) -> None:
    fixture_bundle["matches"].matches.clear()
    fixture_bundle["matches"].rounds.clear()
    use_case = _use_case(fixture_bundle)

    preview = use_case.draw_station_match_poomsaes(
        station_id="station-01",
        category_id="advanced",
        selected_poomsaes=["Taeguk 5", "Taeguk 6", "Taeguk 7"],
        total_rounds=2,
        actor="admin",
    )

    scoreboard = use_case.station_scoreboard("station-01")
    assert scoreboard.has_active_match is False
    assert scoreboard.match_category_id == "advanced"
    assert scoreboard.match_category_label == "Advanced"
    assert scoreboard.match_poomsaes == preview.drawn_poomsaes


def test_station_scoreboard_defaults_category_to_beginners_without_history(fixture_bundle) -> None:
    fixture_bundle["matches"].matches.clear()
    fixture_bundle["matches"].rounds.clear()
    use_case = _use_case(fixture_bundle)

    scoreboard = use_case.station_scoreboard("station-01")
    assert scoreboard.match_category_id == "beginners"
    assert scoreboard.match_category_label == "Beginners"


def test_station_scoreboard_uses_last_started_category_when_no_active_match(fixture_bundle) -> None:
    fixture_bundle["matches"].matches.clear()
    fixture_bundle["matches"].rounds.clear()
    use_case = _use_case(fixture_bundle)

    use_case.start_match(
        station_id="station-01",
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        category_id="black_belts",
        selected_poomsaes=["Koryo", "Keumgang", "Taebaek"],
        total_rounds=2,
        actor="admin",
    )

    fixture_bundle["matches"].matches.clear()
    fixture_bundle["matches"].rounds.clear()

    scoreboard = use_case.station_scoreboard("station-01")
    assert scoreboard.has_active_match is False
    assert scoreboard.match_category_id == "black_belts"
    assert scoreboard.match_category_label == "Black belts"


def test_station_scoreboard_keeps_pending_participants_for_next_match(fixture_bundle) -> None:
    use_case = _use_case(fixture_bundle)

    use_case.save_station_match_competitors(
        station_id="station-01",
        competitor_left_name="Next Red",
        competitor_right_name="Next Blue",
        actor="admin",
    )

    scoreboard = use_case.station_scoreboard("station-01")
    assert scoreboard.has_active_match is True
    assert scoreboard.pending_competitor_left_name == "Next Red"
    assert scoreboard.pending_competitor_right_name == "Next Blue"


def test_start_match_clears_pending_participants_draft(fixture_bundle) -> None:
    fixture_bundle["matches"].matches.clear()
    fixture_bundle["matches"].rounds.clear()
    use_case = _use_case(fixture_bundle)

    use_case.save_station_match_competitors(
        station_id="station-01",
        competitor_left_name="Temporary Red",
        competitor_right_name="Temporary Blue",
        actor="admin",
    )

    use_case.start_match(
        station_id="station-01",
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        category_id="advanced",
        selected_poomsaes=["Taeguk 5", "Taeguk 6"],
        total_rounds=2,
        actor="admin",
    )

    scoreboard = use_case.station_scoreboard("station-01")
    assert scoreboard.has_active_match is True
    assert scoreboard.pending_competitor_left_name is None
    assert scoreboard.pending_competitor_right_name is None


def test_start_match_publishes_new_competitors_event(fixture_bundle) -> None:
    fixture_bundle["matches"].matches.clear()
    fixture_bundle["matches"].rounds.clear()
    realtime = RealtimeRecorderAdapter()
    use_case = AdminViewUseCases(
        station_repository=fixture_bundle["stations"],
        session_repository=fixture_bundle["sessions"],
        match_repository=fixture_bundle["matches"],
        score_event_repository=fixture_bundle["score_events"],
        audit_repository=fixture_bundle["audit"],
        bootstrap_service=_BootstrapStub(),
        credential_service=fixture_bundle["credential_service"],
        credential_generator=_CredentialGeneratorStub(),
        clock=FixedClock(),
        id_generator=fixture_bundle["ids"],
        base_url="http://127.0.0.1:8080",
        environment="test",
        tournament_id="tkd-test",
        protocol_version="v1",
        bootstrap_ttl_seconds=180,
        station_credential_ttl_seconds=3600,
        station_credential_rotation_seconds=20,
        history_retention_matches=10,
        realtime=realtime,
    )

    result = use_case.start_match(
        station_id="station-01",
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        category_id="advanced",
        selected_poomsaes=["Taeguk 5", "Taeguk 6", "Taeguk 7"],
        total_rounds=2,
        actor="admin",
    )

    new_competitors_events = [
        event for event in realtime.events if event["event_type"] == "new_competitors"
    ]
    assert len(new_competitors_events) == 1
    event = new_competitors_events[0]
    assert event["target"] == "station"
    assert event["station_id"] == "station-01"
    assert event["payload"]["matchId"] == result.match_id
    assert event["payload"]["competitorRedName"] == "Competitor A"
    assert event["payload"]["competitorBlueName"] == "Competitor B"
    assert event["payload"]["competitorLeftName"] == "Competitor A"
    assert event["payload"]["competitorRightName"] == "Competitor B"

    active_state_events = [
        event for event in realtime.events if event["event_type"] == "active_match_state"
    ]
    assert len(active_state_events) == 1
    active_state = active_state_events[0]
    assert active_state["payload"]["hasActiveMatch"] is True
    assert active_state["payload"]["matchId"] == result.match_id
    assert active_state["payload"]["competitorRedName"] == "Competitor A"
    assert active_state["payload"]["competitorBlueName"] == "Competitor B"

    judge_settings_events = [
        event for event in realtime.events if event["event_type"] == "judge_settings_updated"
    ]
    assert len(judge_settings_events) == 1
    judge_settings = judge_settings_events[0]["payload"]
    assert judge_settings["defaultRounds"] == 2
    assert judge_settings["defaultStartingScore"] == 4.0
    assert judge_settings["presentationCategoryStartScore"] == 2.0
    assert judge_settings["actionValue1"] == 0.1
    assert judge_settings["actionValue2"] == 0.3


def test_station_scoreboard_ignores_active_match_when_owner_session_is_revoked(fixture_bundle) -> None:
    use_case = _use_case(fixture_bundle)
    fixture_bundle["sessions"].revoke("sess-1")

    scoreboard = use_case.station_scoreboard("station-01")
    assert scoreboard.has_active_match is False
