"""Removed judges (kick before finalizing), judges joining a live match, session replacement and match reset."""

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.unit.test_multi_judge_finalization import (
    _JUDGES,
    _START,
    _finalize_input,
    _score,
    three_judges,
)
from tkd_scorer.application.use_cases._match_scoring import build_match_scoring
from tkd_scorer.application.use_cases.control_match_use_cases import ResetMatchUseCase
from tkd_scorer.application.use_cases.kick_judge_session_use_case import KickJudgeSessionUseCase
from tkd_scorer.domain.entities.common import MatchStatus, SessionStatus
from tkd_scorer.domain.entities.device_session import DeviceSession

__all__ = ["three_judges"]

# Session that replaced Judge 2's session on another device.
_JUDGES.setdefault("sess-2b", "Judge 2")


def _kick(bundle) -> KickJudgeSessionUseCase:
    return KickJudgeSessionUseCase(
        session_repository=bundle["sessions"],
        station_repository=bundle["stations"],
        audit_repository=bundle["audit"],
        realtime=bundle["realtime"],
        clock=bundle["clock"],
        id_generator=bundle["ids"],
        match_repository=bundle["matches"],
        finalization_repository=bundle["finalizations"],
    )


def _scoring(bundle):
    return build_match_scoring(
        match=bundle["matches"].get_match("match-1"),
        score_event_repository=bundle["score_events"],
        session_repository=bundle["sessions"],
        finalization_repository=bundle["finalizations"],
        presentation_category_start=Decimal("2.0"),
    )


def _add_session(bundle, session_id: str, *, minutes_after_start: int, scorecard_session_id: str | None = None):
    bundle["sessions"].save(
        DeviceSession(
            id=session_id,
            station_id="station-01",
            judge_name=_JUDGES.get(session_id, "Judge 4"),
            device_id=f"device-{session_id}",
            token_hash=f"hash::{session_id}",
            status=SessionStatus.ACTIVE,
            created_at=bundle["clock"].now() + timedelta(minutes=minutes_after_start),
            expires_at=None,
            scorecard_session_id=scorecard_session_id,
        )
    )


def _track_judges(bundle, *keys: str) -> None:
    match = bundle["matches"].get_match("match-1")
    match.set_judges(keys)
    bundle["matches"].save_match(match)


@pytest.mark.asyncio
async def test_kicked_judge_stops_counting_and_the_match_closes_when_the_rest_finalized(three_judges) -> None:
    _track_judges(three_judges, "sess-1", "sess-2", "sess-3")
    await _score(three_judges, "sess-1", 1, "-0.3")
    await _score(three_judges, "sess-2", 1, "-0.1")
    await _score(three_judges, "sess-3", 1, "-2.0")
    for session_id, technique in (("sess-1", "3.7"), ("sess-2", "3.9")):
        result = await three_judges["finalize"].execute(
            _finalize_input(session_id, technique, total_events=1, last_sequence=1, key=f"fin-{session_id}")
        )
        assert result.reconciled is True, result.notes
    assert three_judges["matches"].get_match("match-1").status == MatchStatus.IN_PROGRESS

    await _kick(three_judges).execute(station_id="station-01", session_id="sess-3", reason="removed", actor="admin")

    match = three_judges["matches"].get_match("match-1")
    assert match.judges_required == 2
    assert match.removed_session_ids == ("sess-3",)
    assert match.status == MatchStatus.FINISHED
    scoring = _scoring(three_judges)
    removed = next(item for item in scoring.judges if item.session_id == "sess-3")
    assert removed.removed is True
    # Still visible (debug), but its partial scorecard is not consolidated: mean of 3.7 and 3.9.
    assert removed.scorecard.round(1).technique_red == Decimal("2.0")
    assert scoring.result.round(1).technique_red == Decimal("3.80")
    assert (scoring.judges_finalized, scoring.judges_required) == (2, 2)
    closed = [item for item in three_judges["realtime"].events if item["event_type"] == "active_match_state"]
    assert closed[-1]["payload"]["hasActiveMatch"] is False


@pytest.mark.asyncio
async def test_kick_of_a_judge_that_already_finalized_changes_nothing(three_judges) -> None:
    _track_judges(three_judges, "sess-1", "sess-2", "sess-3")
    finalized = await three_judges["finalize"].execute(
        _finalize_input("sess-1", "4.0", total_events=0, last_sequence=0, key="fin-sess-1")
    )
    assert finalized.reconciled is True
    # Released after reconciling; re-activate to check the kick ignores finalized judges.
    three_judges["sessions"].items["sess-1"].status = SessionStatus.ACTIVE

    await _kick(three_judges).execute(station_id="station-01", session_id="sess-1", reason="removed", actor="admin")

    match = three_judges["matches"].get_match("match-1")
    assert match.judges_required == 3
    assert match.removed_session_ids == ()


@pytest.mark.asyncio
async def test_judges_required_never_drops_below_one(fixture_bundle) -> None:
    from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import RealtimeRecorderAdapter

    bundle = {**fixture_bundle, "realtime": RealtimeRecorderAdapter()}
    _track_judges(bundle, "sess-1")

    await _kick(bundle).execute(station_id="station-01", session_id="sess-1", reason="removed", actor="admin")

    match = bundle["matches"].get_match("match-1")
    assert match.judges_required == 1
    assert match.status == MatchStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_judge_joining_a_live_match_counts_from_its_first_score_event(three_judges) -> None:
    _track_judges(three_judges, "sess-1", "sess-2")
    _add_session(three_judges, "sess-4", minutes_after_start=5)
    _JUDGES.setdefault("sess-4", "Judge 4")
    match = three_judges["matches"].get_match("match-1")
    assert match.judges_required == 2
    assert match.is_live(three_judges["sessions"].list_active_by_station("station-01"))

    await _score(three_judges, "sess-4", 1, "-0.1")
    await _score(three_judges, "sess-4", 2, "-0.1")

    match = three_judges["matches"].get_match("match-1")
    assert match.judge_session_ids == ("sess-1", "sess-2", "sess-4")
    assert match.judges_required == 3


@pytest.mark.asyncio
async def test_replacement_session_continues_the_judge_scorecard(three_judges) -> None:
    _track_judges(three_judges, "sess-1", "sess-2", "sess-3")
    await _score(three_judges, "sess-2", 1, "-0.1")
    # Judge 2 moves to another device: the old session is revoked, the new one inherits its scorecard.
    three_judges["sessions"].revoke("sess-2")
    _add_session(three_judges, "sess-2b", minutes_after_start=5, scorecard_session_id="sess-2")
    await _score(three_judges, "sess-2b", 1, "-0.2")

    match = three_judges["matches"].get_match("match-1")
    assert match.judges_required == 3
    assert match.judge_session_ids == ("sess-1", "sess-2", "sess-3")
    scoring = _scoring(three_judges)
    judge_two = [item for item in scoring.judges if item.judge_name == "Judge 2"]
    assert len(judge_two) == 1
    assert judge_two[0].session_ids == ("sess-2", "sess-2b")
    assert judge_two[0].scorecard.round(1).technique_red == Decimal("3.7")

    # The device that holds both events (same device reconnecting) reconciles with the single scorecard.
    result = await three_judges["finalize"].execute(
        _finalize_input("sess-2b", "3.7", total_events=2, last_sequence=1, key="fin-sess-2b")
    )
    assert result.reconciled is True, result.notes
    assert (result.judges_finalized, result.judges_required) == (1, 3)


@pytest.mark.asyncio
async def test_admin_reset_match_clears_finalizations_so_judges_finalize_again(three_judges) -> None:
    _track_judges(three_judges, "sess-1", "sess-2", "sess-3")
    await _score(three_judges, "sess-1", 1, "-0.3")
    await three_judges["finalize"].execute(
        _finalize_input("sess-1", "3.7", total_events=1, last_sequence=1, key="fin-sess-1")
    )
    assert len(three_judges["finalizations"].items) == 1
    reset = ResetMatchUseCase(
        match_repository=three_judges["matches"],
        score_event_repository=three_judges["score_events"],
        audit_repository=three_judges["audit"],
        realtime=three_judges["realtime"],
        clock=three_judges["clock"],
        id_generator=three_judges["ids"],
        finalization_repository=three_judges["finalizations"],
        session_repository=three_judges["sessions"],
    )

    await reset.execute("match-1", "admin")

    assert three_judges["finalizations"].items == {}
    match = three_judges["matches"].get_match("match-1")
    assert match.status == MatchStatus.IN_PROGRESS
    # Judge 1 was released after finalizing: the judges counted now are the connected ones.
    assert set(match.judge_session_ids) == {"sess-2", "sess-3"}
    assert match.judges_required == 2
    again = await three_judges["finalize"].execute(
        _finalize_input("sess-2", "4.0", total_events=0, last_sequence=0, key="fin-sess-2-after-reset")
    )
    assert again.idempotent_replay is False
    assert again.judges_finalized == 1
    assert _START < match.started_at
