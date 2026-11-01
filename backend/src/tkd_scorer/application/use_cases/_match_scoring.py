"""Builds the per-judge scorecards and the consolidated result of a shared match from stored data."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from tkd_scorer.domain.entities.common import MatchStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.entities.match import Match
from tkd_scorer.domain.entities.score_event import FinalizationRecord, ScoreEvent
from tkd_scorer.domain.services.judge_consolidation import ConsolidatedMatch, consolidate_scorecards
from tkd_scorer.domain.services.judge_scorecard import (
    JudgeScorecard,
    build_judge_scorecard,
    judge_aliases,
)
from tkd_scorer.ports.repositories.finalization_repository_port import FinalizationRepositoryPort
from tkd_scorer.ports.repositories.score_event_repository_port import ScoreEventRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort


@dataclass(frozen=True)
class MatchJudge:
    # Scorecard identity of the judge (DeviceSession.scorecard_key): its first session.
    session_id: str
    judge_name: str
    alias: str
    finalization: FinalizationRecord | None
    scorecard: JudgeScorecard
    # Sessions that wrote to this scorecard, in connection order (more than one after a session replacement).
    session_ids: tuple[str, ...] = ()
    # Removed by the operator before finalizing: shown, but not counted nor consolidated.
    removed: bool = False

    @property
    def finalized(self) -> bool:
        return self.finalization is not None

    @property
    def reconciled(self) -> bool:
        return self.finalization is not None and self.finalization.status == MatchStatus.FINISHED.value


@dataclass(frozen=True)
class MatchScoring:
    match: Match
    judges: list[MatchJudge]
    events: list[ScoreEvent]
    live: ConsolidatedMatch
    final: ConsolidatedMatch | None
    judges_finalized: int
    judges_required: int

    @property
    def all_finalized(self) -> bool:
        return self.judges_finalized >= self.judges_required

    @property
    def result(self) -> ConsolidatedMatch:
        """Official result once available, otherwise the live partial."""
        return self.final if self.final is not None else self.live

    def alias_for(self, session_id: str) -> str | None:
        return next(
            (item.alias for item in self.judges if session_id == item.session_id or session_id in item.session_ids),
            None,
        )


class ScorecardKeys:
    """Maps session IDs to their scorecard identity (DeviceSession.scorecard_key), with a small cache."""

    def __init__(self, session_repository: SessionRepositoryPort) -> None:
        self._session_repository = session_repository
        self._sessions: dict[str, DeviceSession | None] = {}

    def session(self, session_id: str) -> DeviceSession | None:
        if session_id not in self._sessions:
            self._sessions[session_id] = self._session_repository.get_by_id(session_id)
        return self._sessions[session_id]

    def remember(self, session: DeviceSession) -> None:
        self._sessions.setdefault(session.id, session)

    def key(self, session_id: str) -> str:
        session = self.session(session_id)
        return session.scorecard_key if session is not None else session_id

    def chain(self, key: str, session_ids: Iterable[str]) -> tuple[str, ...]:
        """The given sessions that belong to identity key, in connection order."""
        members = {item for item in session_ids if self.key(item) == key}

        def order(session_id: str) -> tuple[datetime, str]:
            session = self.session(session_id)
            created = _as_utc(session.created_at) if session is not None else datetime.max.replace(tzinfo=UTC)
            return created, session_id

        return tuple(sorted(members, key=order))


def latest_finalizations_by_judge(
    *,
    match: Match,
    finalizations: Iterable[FinalizationRecord],
    keys: ScorecardKeys,
) -> dict[str, FinalizationRecord]:
    """Latest finalization per counted judge (scorecard identity); removed judges are left out."""
    latest: dict[str, FinalizationRecord] = {}
    for item in finalizations:
        key = keys.key(item.session_id)
        if key in match.removed_session_ids:
            continue
        latest[key] = item
    return latest


def close_match_when_complete(*, match: Match, latest_by_judge: dict[str, FinalizationRecord], now) -> bool:
    """Closes a running shared match once every counted judge finalized; returns True when it closed.

    FINISHED when every finalization reconciled, otherwise FINALIZATION_PENDING.
    """
    if match.status not in (MatchStatus.IN_PROGRESS, MatchStatus.FINALIZATION_PENDING):
        return False
    if len(latest_by_judge) < max(1, match.judges_required):
        return False
    if all(item.status == MatchStatus.FINISHED.value for item in latest_by_judge.values()):
        match.finish(now)
    else:
        match.mark_finalization_pending()
    return True


def build_match_scoring(
    *,
    match: Match,
    score_event_repository: ScoreEventRepositoryPort,
    session_repository: SessionRepositoryPort,
    finalization_repository: FinalizationRepositoryPort | None,
    presentation_category_start: Decimal,
    station_sessions: Iterable[DeviceSession] = (),
) -> MatchScoring:
    """Scorecards per judge of the match and their consolidation.

    Judges are the scorecard identities of the sessions that scored or finalized the match, plus
    station_sessions (the judges connected to the station while the match is live). A judge that replaced
    its session keeps one scorecard with the events of all its sessions. Judges are ordered by their first
    connection to the station (creation of their first session) and named J1..Jn.

    Rounds of a judge: the rounds reported on finalize plus the rounds with events; a judge that has not
    finalized yet covers every round opened so far (start values where it has no events).

    Judges removed by the operator (match.removed_session_ids) stay in the list (marked removed) but are
    not counted as finalized and are left out of the consolidation.
    """
    events = score_event_repository.list_for_match(match.id)
    finalization_records = finalization_repository.list_for_match(match.id) if finalization_repository else []
    keys = ScorecardKeys(session_repository)
    station_sessions = list(station_sessions)
    for session in station_sessions:
        keys.remember(session)

    session_ids: list[str] = []
    for session_id in [
        *(item.id for item in station_sessions),
        *(item.session_id for item in sorted(events, key=lambda event: event.received_at)),
        *(item.session_id for item in finalization_records),
    ]:
        if session_id not in session_ids:
            session_ids.append(session_id)

    first_seen: dict[str, datetime] = {}
    names: dict[str, str] = {}
    for session_id in session_ids:
        key = keys.key(session_id)
        session = keys.session(session_id)
        if session is not None:
            seen = session.created_at
            names[key] = session.judge_name
        else:
            seen = min(
                (item.received_at for item in events if item.session_id == session_id),
                default=next(
                    (item.created_at for item in finalization_records if item.session_id == session_id),
                    match.created_at,
                ),
            )
            names.setdefault(
                key, next((item.judge_name for item in events if item.session_id == session_id), session_id)
            )
        root = keys.session(key)
        if root is not None:
            seen = min(_as_utc(seen), _as_utc(root.created_at))
        first_seen[key] = min(_as_utc(seen), first_seen.get(key, _as_utc(seen)))

    ordered_keys = sorted(names.keys(), key=lambda key: (first_seen[key], key))
    aliases = judge_aliases(ordered_keys)
    latest_finalization: dict[str, FinalizationRecord] = {}
    for item in finalization_records:
        latest_finalization[keys.key(item.session_id)] = item

    opened_round = max(
        [
            1,
            int(match.current_round or 1),
            *(item.round_number for item in events),
            *(number for item in finalization_records for number in item.round_numbers),
        ]
    )
    live_rounds = range(1, opened_round + 1)

    judges: list[MatchJudge] = []
    for key in ordered_keys:
        chain = keys.chain(key, session_ids)
        finalization = latest_finalization.get(key)
        event_rounds = {item.round_number for item in events if item.session_id in chain}
        if finalization is not None and finalization.round_numbers:
            round_numbers = set(finalization.round_numbers) | event_rounds
        else:
            round_numbers = set(live_rounds) | event_rounds
        judges.append(
            MatchJudge(
                session_id=key,
                judge_name=names[key],
                alias=aliases[key],
                finalization=finalization,
                scorecard=build_judge_scorecard(
                    session_id=key,
                    judge_name=names[key],
                    events=events,
                    round_numbers=round_numbers,
                    technique_start=match.starting_score,
                    presentation_category_start=presentation_category_start,
                    session_ids=chain,
                ),
                session_ids=chain,
                removed=key in match.removed_session_ids,
            )
        )

    judges_required = max(1, int(match.judges_required))
    counted = [item for item in judges if not item.removed]
    live = consolidate_scorecards([item.scorecard for item in counted])
    finalized = [item.scorecard for item in counted if item.finalized]
    final: ConsolidatedMatch | None = None
    if len(finalized) >= judges_required:
        final = consolidate_scorecards(finalized)
    elif match.status != MatchStatus.IN_PROGRESS:
        # Closed by the operator before every judge finalized: use the judges that did, or the live data.
        final = consolidate_scorecards(finalized) if finalized else live

    return MatchScoring(
        match=match,
        judges=judges,
        events=events,
        live=live,
        final=final,
        judges_finalized=len(finalized),
        judges_required=judges_required,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
