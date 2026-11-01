from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from tkd_scorer.domain.entities.common import MatchStatus, RoundStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.exceptions.errors import ValidationError


@dataclass
class Match:
    id: str
    station_id: str
    session_id: str
    judge_name: str
    competitor_left_name: str
    competitor_right_name: str
    total_rounds: int
    current_round: int
    starting_score: Decimal
    status: MatchStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # Judge sessions expected to finalize before the shared match is closed (one per judge).
    judges_required: int = 1
    # Scorecard identities (DeviceSession.scorecard_key) counted as judges of the match: the judges connected
    # when it started plus the ones that joined later and sent a score event. Empty for matches stored by
    # older versions, which only know judges_required.
    judge_session_ids: tuple[str, ...] = ()
    # Counted judges removed by the operator before finalizing: they no longer count and their partial
    # scorecard is left out of the consolidation.
    removed_session_ids: tuple[str, ...] = ()

    def start(self, at: datetime) -> None:
        if self.status not in (MatchStatus.PENDING, MatchStatus.IN_PROGRESS):
            raise ValidationError("Match cannot be started from current status")
        self.status = MatchStatus.IN_PROGRESS
        if self.started_at is None:
            self.started_at = at

    def next_round(self) -> int:
        if self.current_round >= self.total_rounds:
            raise ValidationError("Cannot move beyond total rounds")
        self.current_round += 1
        return self.current_round

    def mark_finalization_pending(self) -> None:
        if self.status not in (MatchStatus.IN_PROGRESS, MatchStatus.FINALIZATION_PENDING):
            raise ValidationError("Only in-progress matches can be finalized")
        self.status = MatchStatus.FINALIZATION_PENDING

    def is_live(self, active_sessions: Iterable[DeviceSession]) -> bool:
        """Whether the station still runs this match.

        The match is shared by every judge of the station, so it stays live while its bound session or
        any judge session that was already open when it started is active. A judge that finalizes (and
        is released) does not end the match for the others; a match whose judges all left does.
        """
        if self.status not in (MatchStatus.IN_PROGRESS, MatchStatus.FINALIZATION_PENDING):
            return False
        reference = _as_utc(self.started_at or self.created_at)
        for session in active_sessions:
            if not session.is_active or session.station_id != self.station_id:
                continue
            if session.id == self.session_id or _as_utc(session.created_at) <= reference:
                return True
            if self.counts_judge(session.scorecard_key, first_connected_at=session.created_at):
                return True
        return False

    def counts_judge(self, scorecard_key: str, *, first_connected_at: datetime) -> bool:
        """Whether this judge (scorecard identity) is one of the judges the match waits for."""
        if scorecard_key in self.removed_session_ids:
            return False
        if self.judge_session_ids:
            return scorecard_key in self.judge_session_ids
        # Older matches: the judges connected when the match started.
        reference = _as_utc(self.started_at or self.created_at)
        return scorecard_key == self.session_id or _as_utc(first_connected_at) <= reference

    def add_judge(self, scorecard_key: str) -> bool:
        """Counts a judge that joined after the start (on its first score event). Returns True when added."""
        if not self.judge_session_ids or scorecard_key in self.judge_session_ids:
            return False
        if scorecard_key in self.removed_session_ids:
            return False
        self.judge_session_ids = (*self.judge_session_ids, scorecard_key)
        self._refresh_judges_required()
        return True

    def remove_judge(self, scorecard_key: str) -> None:
        """Stops counting a judge removed by the operator; judges_required never drops below 1."""
        if scorecard_key in self.removed_session_ids:
            return
        self.removed_session_ids = (*self.removed_session_ids, scorecard_key)
        if self.judge_session_ids:
            self._refresh_judges_required()
        else:
            self.judges_required = max(1, int(self.judges_required) - 1)

    def set_judges(self, scorecard_keys: Iterable[str]) -> None:
        """Judges of a (re)started match: the judges connected now; nobody is removed."""
        self.judge_session_ids = tuple(dict.fromkeys(scorecard_keys))
        self.removed_session_ids = ()
        self.judges_required = max(1, len(self.judge_session_ids))

    def _refresh_judges_required(self) -> None:
        counted = [key for key in self.judge_session_ids if key not in self.removed_session_ids]
        self.judges_required = max(1, len(counted))

    def finish(self, at: datetime) -> None:
        self.status = MatchStatus.FINISHED
        self.finished_at = at

    def reset_round(self) -> None:
        if self.status not in (MatchStatus.IN_PROGRESS, MatchStatus.FINALIZATION_PENDING):
            raise ValidationError("Cannot reset round for current match status")

    def reset_match(self, _at: datetime) -> None:
        self.current_round = 1
        self.status = MatchStatus.PENDING
        self.started_at = None
        self.finished_at = None


@dataclass
class MatchRound:
    id: str
    match_id: str
    round_number: int
    status: RoundStatus
    started_at: datetime | None = None
    ended_at: datetime | None = None

    def start(self, at: datetime) -> None:
        self.status = RoundStatus.ACTIVE
        self.started_at = at

    def finish(self, at: datetime) -> None:
        self.status = RoundStatus.FINISHED
        self.ended_at = at


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
