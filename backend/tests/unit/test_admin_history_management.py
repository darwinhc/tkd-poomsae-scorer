from datetime import datetime
from decimal import Decimal

import pytest

from tests.unit.fakes import FixedClock
from tkd_scorer.application.use_cases.admin_view_use_cases import AdminViewUseCases
from tkd_scorer.domain.entities.common import MatchStatus
from tkd_scorer.domain.entities.match import Match
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
        history_retention_matches=100,
    )


def test_delete_history_match_removes_finished_match(fixture_bundle) -> None:
    use_case = _use_case(fixture_bundle)
    match = fixture_bundle["matches"].get_match("match-1")
    assert match is not None
    match.status = MatchStatus.FINISHED
    fixture_bundle["matches"].save_match(match)

    use_case.delete_history_match(match_id="match-1", actor="admin")

    assert fixture_bundle["matches"].get_match("match-1") is None
    assert any(
        item.category == "history" and item.action == "delete_match" and item.subject_id == "match-1"
        for item in fixture_bundle["audit"].items
    )


def test_delete_history_match_rejects_active_match(fixture_bundle) -> None:
    use_case = _use_case(fixture_bundle)

    with pytest.raises(ConflictError):
        use_case.delete_history_match(match_id="match-1", actor="admin")


def test_delete_history_match_allows_pending_without_active_session(fixture_bundle) -> None:
    use_case = _use_case(fixture_bundle)
    match = fixture_bundle["matches"].get_match("match-1")
    assert match is not None
    match.status = MatchStatus.FINALIZATION_PENDING
    fixture_bundle["matches"].save_match(match)
    fixture_bundle["sessions"].revoke("sess-1")

    use_case.delete_history_match(match_id="match-1", actor="admin")

    assert fixture_bundle["matches"].get_match("match-1") is None


def test_delete_all_history_matches_deletes_only_non_active(fixture_bundle) -> None:
    use_case = _use_case(fixture_bundle)
    clock = fixture_bundle["clock"]

    finished = Match(
        id="match-2",
        station_id="station-01",
        session_id="sess-1",
        judge_name="Judge 1",
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        total_rounds=2,
        current_round=2,
        starting_score=Decimal("10.0"),
        status=MatchStatus.FINISHED,
        created_at=clock.now(),
        started_at=clock.now(),
        finished_at=clock.now(),
    )
    cancelled = Match(
        id="match-3",
        station_id="station-01",
        session_id="sess-1",
        judge_name="Judge 1",
        competitor_left_name="Competitor A",
        competitor_right_name="Competitor B",
        total_rounds=2,
        current_round=1,
        starting_score=Decimal("10.0"),
        status=MatchStatus.CANCELLED,
        created_at=clock.now(),
    )
    fixture_bundle["matches"].save_match(finished)
    fixture_bundle["matches"].save_match(cancelled)

    deleted, skipped_active = use_case.delete_all_history_matches(actor="admin")

    assert deleted == 2
    assert skipped_active == 1
    assert fixture_bundle["matches"].get_match("match-1") is not None
    assert fixture_bundle["matches"].get_match("match-2") is None
    assert fixture_bundle["matches"].get_match("match-3") is None
