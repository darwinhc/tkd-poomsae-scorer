from decimal import Decimal

from tkd_scorer.application.dto.control_dto import CommandAck
from tkd_scorer.application.dto.match_dto import MatchSummaryOutput
from tkd_scorer.application.use_cases._match_scoring import build_match_scoring
from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import AthleteSide, MatchStatus, RoundStatus
from tkd_scorer.domain.entities.match import MatchRound
from tkd_scorer.domain.exceptions.errors import NotFoundError, UnauthorizedError, ValidationError
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort
from tkd_scorer.ports.realtime.realtime_port import RealtimePort
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.finalization_repository_port import FinalizationRepositoryPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.score_event_repository_port import ScoreEventRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort


class NextRoundUseCase:
    def __init__(
        self,
        *,
        match_repository: MatchRepositoryPort,
        audit_repository: AuditRepositoryPort,
        realtime: RealtimePort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._match_repository = match_repository
        self._audit_repository = audit_repository
        self._realtime = realtime
        self._clock = clock
        self._id_generator = id_generator

    async def execute(self, match_id: str, actor: str, *, station_id: str | None = None) -> CommandAck:
        """station_id: the station of the calling judge session (None for the administrator)."""
        match = self._match_repository.get_match(match_id)
        if match is None:
            raise NotFoundError("Match not found")
        _require_station(match.station_id, station_id)

        now = self._clock.now()
        current_round = self._match_repository.get_round(match_id, match.current_round)
        if current_round:
            current_round.finish(now)
            self._match_repository.upsert_round(current_round)

        next_round_number = match.next_round()
        next_round = MatchRound(
            id=self._id_generator.new("round"),
            match_id=match.id,
            round_number=next_round_number,
            status=RoundStatus.ACTIVE,
            started_at=now,
        )
        self._match_repository.upsert_round(next_round)
        self._match_repository.save_match(match)

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="next_round",
                subject_id=match.id,
                actor=actor,
                details=f"round={next_round_number}",
                occurred_at=now,
            )
        )

        await self._realtime.publish_to_station(
            match.station_id,
            "round_changed",
            {"matchId": match.id, "currentRound": next_round_number},
        )
        return CommandAck(match_id=match.id, message="Round advanced")


class ResetRoundUseCase:
    def __init__(
        self,
        *,
        match_repository: MatchRepositoryPort,
        score_event_repository: ScoreEventRepositoryPort,
        audit_repository: AuditRepositoryPort,
        realtime: RealtimePort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._match_repository = match_repository
        self._score_event_repository = score_event_repository
        self._audit_repository = audit_repository
        self._realtime = realtime
        self._clock = clock
        self._id_generator = id_generator

    async def execute(self, match_id: str, actor: str) -> CommandAck:
        match = self._match_repository.get_match(match_id)
        if match is None:
            raise NotFoundError("Match not found")
        if match.status not in (MatchStatus.IN_PROGRESS, MatchStatus.FINALIZATION_PENDING):
            raise ValidationError("Match status does not allow reset")

        self._score_event_repository.delete_for_match_round(match_id, match.current_round)
        now = self._clock.now()
        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="reset_round",
                subject_id=match_id,
                actor=actor,
                details=f"round={match.current_round}",
                occurred_at=now,
            )
        )
        await self._realtime.publish_to_station(
            match.station_id,
            "reset_round",
            {"matchId": match_id, "round": match.current_round},
        )
        return CommandAck(match_id=match_id, message="Round reset")


class ResetMatchUseCase:
    """Administrator reset of a shared match: it restarts as if it had just been started.

    Deletes every judge's score events and finalization records (so the judges can finalize again) and
    counts as judges the judge sessions connected to the station now (nobody is removed any more).
    """

    def __init__(
        self,
        *,
        match_repository: MatchRepositoryPort,
        score_event_repository: ScoreEventRepositoryPort,
        audit_repository: AuditRepositoryPort,
        realtime: RealtimePort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
        finalization_repository: FinalizationRepositoryPort | None = None,
        session_repository: SessionRepositoryPort | None = None,
    ) -> None:
        self._finalization_repository = finalization_repository
        self._session_repository = session_repository
        self._match_repository = match_repository
        self._score_event_repository = score_event_repository
        self._audit_repository = audit_repository
        self._realtime = realtime
        self._clock = clock
        self._id_generator = id_generator

    async def execute(self, match_id: str, actor: str) -> CommandAck:
        match = self._match_repository.get_match(match_id)
        if match is None:
            raise NotFoundError("Match not found")
        now = self._clock.now()

        self._score_event_repository.delete_for_match(match_id)
        if self._finalization_repository is not None:
            self._finalization_repository.delete_for_match(match_id)
        match.reset_match(now)
        match.start(now)
        if self._session_repository is not None and match.judge_session_ids:
            match.set_judges(
                item.scorecard_key for item in self._session_repository.list_active_by_station(match.station_id)
            )
        self._match_repository.save_match(match)

        first_round = self._match_repository.get_round(match_id, 1)
        if first_round is None:
            first_round = MatchRound(
                id=self._id_generator.new("round"),
                match_id=match_id,
                round_number=1,
                status=RoundStatus.ACTIVE,
                started_at=now,
            )
        else:
            first_round.status = RoundStatus.ACTIVE
            first_round.started_at = now
            first_round.ended_at = None
        self._match_repository.upsert_round(first_round)

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="reset_match",
                subject_id=match_id,
                actor=actor,
                details="full reset",
                occurred_at=now,
            )
        )

        await self._realtime.publish_to_station(match.station_id, "reset_match", {"matchId": match_id})
        return CommandAck(match_id=match_id, message="Match reset")


class GetMatchSummaryUseCase:
    def __init__(
        self,
        *,
        match_repository: MatchRepositoryPort,
        score_event_repository: ScoreEventRepositoryPort,
        session_repository: SessionRepositoryPort,
        finalization_repository: FinalizationRepositoryPort | None = None,
        presentation_category_start_score: Decimal = Decimal("2.0"),
    ) -> None:
        self._match_repository = match_repository
        self._score_event_repository = score_event_repository
        self._session_repository = session_repository
        self._finalization_repository = finalization_repository
        self._presentation_category_start_score = Decimal(str(presentation_category_start_score))

    def execute(self, match_id: str, *, station_id: str | None = None) -> MatchSummaryOutput:
        """station_id: the station of the calling judge session (None for the administrator)."""
        match = self._match_repository.get_match(match_id)
        if match is None:
            raise NotFoundError("Match not found")
        _require_station(match.station_id, station_id)

        # Consolidated across the judges of the shared match (live partial until every judge finalizes).
        scoring = build_match_scoring(
            match=match,
            score_event_repository=self._score_event_repository,
            session_repository=self._session_repository,
            finalization_repository=self._finalization_repository,
            presentation_category_start=self._presentation_category_start_score,
        )
        result = scoring.result

        return MatchSummaryOutput(
            match_id=match.id,
            station_id=match.station_id,
            judge_name=match.judge_name,
            status=match.status.value,
            current_round=match.current_round,
            total_rounds=match.total_rounds,
            red_score=result.score(AthleteSide.RED),
            blue_score=result.score(AthleteSide.BLUE),
            total_events=len(scoring.events),
        )


def _require_station(match_station_id: str, caller_station_id: str | None) -> None:
    if caller_station_id is not None and caller_station_id != match_station_id:
        raise UnauthorizedError("Match/station mismatch")
