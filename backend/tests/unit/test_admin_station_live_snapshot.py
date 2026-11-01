from datetime import datetime

from tests.unit.fakes import FixedClock
from tkd_scorer.application.use_cases.admin_view_use_cases import AdminViewUseCases


class _BootstrapStub:
    def issue_bootstrap_token(self, *, tournament_id: str, expires_at: datetime) -> str:
        return f"bootstrap::{tournament_id}"

    def validate_bootstrap_token(self, token: str) -> dict[str, str]:
        return {"token": token}


class _CredentialGeneratorStub:
    def generate(self, *, length: int = 6) -> str:
        return "9" * length


def test_station_live_snapshot_handles_naive_updated_at_without_crashing(fixture_bundle) -> None:
    station = fixture_bundle["stations"].get_by_id("station-01")
    assert station is not None
    station.updated_at = datetime(2026, 3, 18, 12, 0, 0)
    fixture_bundle["stations"].save(station)

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
    )

    snapshot = use_case.station_live_snapshot(
        station_id="station-01",
        rotate_credential=True,
        actor="test",
        reveal_credential=False,
    )
    assert snapshot.station_id == "station-01"
    assert '"stationId": "station-01"' in snapshot.bootstrap_payload_json
    assert '"stationName": "Station 01"' in snapshot.bootstrap_payload_json
