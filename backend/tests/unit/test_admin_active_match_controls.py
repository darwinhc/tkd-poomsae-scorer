from datetime import datetime

from tests.unit.fakes import FixedClock
from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import RealtimeRecorderAdapter
from tkd_scorer.application.use_cases.admin_view_use_cases import AdminViewUseCases
from tkd_scorer.domain.entities.common import MatchStatus, RoundStatus


class _BootstrapStub:
    def issue_bootstrap_token(self, *, tournament_id: str, expires_at: datetime) -> str:
        return f"bootstrap::{tournament_id}"

    def validate_bootstrap_token(self, token: str) -> dict[str, str]:
        return {"token": token}


class _CredentialGeneratorStub:
    def generate(self, *, length: int = 6) -> str:
        return "9" * length


def _use_case(fixture_bundle, realtime=None) -> AdminViewUseCases:
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
        realtime=realtime,
    )


def test_finalize_active_match_allows_manual_finish_while_round_is_running(fixture_bundle) -> None:
    use_case = _use_case(fixture_bundle)
    before = use_case.active_match("station-01")
    assert before is not None
    assert before.can_finalize_match is True

    use_case.start_active_round(station_id="station-01", actor="admin")
    use_case.finalize_active_match(station_id="station-01", actor="admin")

    match = fixture_bundle["matches"].get_match("match-1")
    assert match is not None
    assert match.status == MatchStatus.FINISHED
    assert match.finished_at is not None

    round_one = fixture_bundle["matches"].get_round("match-1", 1)
    assert round_one is not None
    assert round_one.status == RoundStatus.FINISHED
    assert round_one.ended_at is not None

    assert use_case.active_match("station-01") is None


def test_finalize_active_match_publishes_active_match_state_false(fixture_bundle) -> None:
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

    use_case.finalize_active_match(station_id="station-01", actor="admin")

    active_state_events = [
        event for event in realtime.events if event["event_type"] == "active_match_state"
    ]
    assert len(active_state_events) == 1
    payload = active_state_events[0]["payload"]
    assert payload["hasActiveMatch"] is False
    assert payload["matchId"] == "match-1"


def test_reset_active_round_tells_the_judges_to_delete_the_same_round(fixture_bundle) -> None:
    # The server deletes the round's events; the phones must delete theirs too or they stop reconciling.
    realtime = RealtimeRecorderAdapter()
    use_case = _use_case(fixture_bundle, realtime=realtime)

    use_case.reset_active_round(station_id="station-01", actor="admin")

    reset_events = [event for event in realtime.events if event["event_type"] == "reset_round"]
    assert len(reset_events) == 1
    assert reset_events[0]["station_id"] == "station-01"
    assert reset_events[0]["payload"] == {"matchId": "match-1", "round": 1}
