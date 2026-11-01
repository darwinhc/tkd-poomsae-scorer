from tkd_scorer.application.dto.match_dto import CreateMatchInput
from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import MatchStatus, RoundStatus
from tkd_scorer.domain.entities.match import Match, MatchRound
from tkd_scorer.domain.exceptions.errors import NotFoundError, UnauthorizedError, ValidationError
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort


class CreateMatchUseCase:
    def __init__(
        self,
        *,
        match_repository: MatchRepositoryPort,
        session_repository: SessionRepositoryPort,
        audit_repository: AuditRepositoryPort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._match_repository = match_repository
        self._session_repository = session_repository
        self._audit_repository = audit_repository
        self._clock = clock
        self._id_generator = id_generator

    def execute(self, request: CreateMatchInput) -> Match:
        if request.total_rounds <= 0:
            raise ValidationError("totalRounds must be greater than zero")

        session = self._session_repository.get_by_id(request.session_id)
        if session is None:
            raise NotFoundError("Session not found")
        if session.station_id != request.station_id:
            raise UnauthorizedError("Session/station mismatch")

        now = self._clock.now()
        match = Match(
            id=self._id_generator.new("match"),
            station_id=request.station_id,
            session_id=request.session_id,
            judge_name=request.judge_name,
            competitor_left_name=request.competitor_left_name,
            competitor_right_name=request.competitor_right_name,
            total_rounds=request.total_rounds,
            current_round=1,
            starting_score=request.starting_score,
            status=MatchStatus.PENDING,
            created_at=now,
        )
        match.set_judges([session.scorecard_key])
        match.start(now)
        self._match_repository.save_match(match)

        round_entity = MatchRound(
            id=self._id_generator.new("round"),
            match_id=match.id,
            round_number=1,
            status=RoundStatus.ACTIVE,
            started_at=now,
        )
        self._match_repository.upsert_round(round_entity)

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="match",
                action="create",
                subject_id=match.id,
                actor=request.judge_name,
                details=f"station_id={request.station_id}",
                occurred_at=now,
            )
        )
        return match
