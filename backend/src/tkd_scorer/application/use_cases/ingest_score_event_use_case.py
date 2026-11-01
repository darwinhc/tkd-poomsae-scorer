import logging
from decimal import Decimal

from tkd_scorer.application.dto.score_dto import IngestScoreEventInput, IngestScoreEventOutput
from tkd_scorer.application.use_cases._helpers import from_json_payload, to_json_payload
from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import AthleteSide, MatchStatus
from tkd_scorer.domain.entities.score_event import IdempotencyRecord, ScoreEvent
from tkd_scorer.domain.exceptions.errors import MatchClosedError, UnauthorizedError, ValidationError
from tkd_scorer.domain.services.judge_scorecard import (
    apply_delta,
    parse_score_target,
    running_target_score,
    target_bounds,
)
from tkd_scorer.domain.value_objects.score import ScoreDelta
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort
from tkd_scorer.ports.realtime.realtime_port import RealtimePort
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.idempotency_repository_port import IdempotencyRepositoryPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.score_event_repository_port import ScoreEventRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort


class IngestScoreEventUseCase:
    def __init__(
        self,
        *,
        idempotency_repository: IdempotencyRepositoryPort,
        session_repository: SessionRepositoryPort,
        match_repository: MatchRepositoryPort,
        score_event_repository: ScoreEventRepositoryPort,
        audit_repository: AuditRepositoryPort,
        realtime: RealtimePort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
        presentation_category_start_score: Decimal = Decimal("2.0"),
    ) -> None:
        self._presentation_category_start_score = Decimal(str(presentation_category_start_score))
        self._idempotency_repository = idempotency_repository
        self._session_repository = session_repository
        self._match_repository = match_repository
        self._score_event_repository = score_event_repository
        self._audit_repository = audit_repository
        self._realtime = realtime
        self._clock = clock
        self._id_generator = id_generator
        self._logger = logging.getLogger("tkd_scorer.use_case.ingest_score_event")

    async def execute(self, request: IngestScoreEventInput) -> IngestScoreEventOutput:
        existing = self._idempotency_repository.get(request.idempotency_key)
        if existing is not None:
            payload = from_json_payload(existing.response_payload)
            return IngestScoreEventOutput(
                event_id=payload["event_id"],
                idempotent_replay=True,
                sequence=payload["sequence"],
                score_before=Decimal(payload["score_before"]),
                score_after=Decimal(payload["score_after"]),
                received_at=self._clock.now(),
            )

        session = self._session_repository.get_by_id(request.session_id)
        if session is None:
            raise UnauthorizedError("Session not found")
        if session.station_id != request.station_id:
            raise UnauthorizedError("Session/station mismatch")
        if session.judge_name != request.judge_name:
            raise UnauthorizedError("Judge name mismatch with active session")

        match_id = request.match_id.strip()
        if not match_id:
            raise ValidationError("matchId is required")
        match = self._match_repository.get_match(match_id)
        if match is None:
            raise ValidationError("matchId must reference an existing backend match")
        if match.station_id != request.station_id:
            raise UnauthorizedError("Match/station mismatch")
        if match.status in (MatchStatus.FINISHED, MatchStatus.CANCELLED):
            # Definitive: the operator closed the match; the app stops retrying on this code.
            raise MatchClosedError("Match is closed and no longer accepts score events")
        if match.status not in (MatchStatus.IN_PROGRESS, MatchStatus.FINALIZATION_PENDING):
            raise ValidationError("Match is not in a score-accepting status")

        side = AthleteSide(request.athlete_side)
        target = parse_score_target(request.score_target)
        delta = ScoreDelta(request.score_delta)
        if request.sequence <= 0:
            raise ValidationError("Sequence must be greater than zero")
        bounds = target_bounds(
            target,
            technique_start=match.starting_score,
            presentation_category_start=self._presentation_category_start_score,
        )

        # Every judge (session) has its own sequence and its own running scores; events of the other judges
        # of the shared match are not mixed in.
        judge_events = [
            event
            for event in self._score_event_repository.list_for_match(match.id)
            if event.session_id == request.session_id
        ]
        same_sequence_event = next(
            (event for event in judge_events if event.sequence == request.sequence),
            None,
        )
        if same_sequence_event is not None:
            if (
                same_sequence_event.round_number == request.round_number
                and same_sequence_event.athlete_side == side
                and same_sequence_event.score_target == target
                and same_sequence_event.score_delta == delta.value
            ):
                self._logger.info(
                    "score_event_sequence_replay_detected station_id=%s session_id=%s match_id=%s sequence=%s stored_event_id=%s requested_event_id=%s",
                    request.station_id,
                    request.session_id,
                    match.id,
                    request.sequence,
                    same_sequence_event.event_id,
                    request.event_id,
                )
                score_before = running_target_score(
                    events=judge_events,
                    side=side,
                    round_number=request.round_number,
                    target=target,
                    bounds=bounds,
                    before_sequence=request.sequence,
                )
                score_after = apply_delta(score_before, delta.value, bounds)
                now = self._clock.now()
                self._save_idempotent_response(
                    idempotency_key=request.idempotency_key,
                    event_id=same_sequence_event.event_id,
                    sequence=request.sequence,
                    score_before=score_before,
                    score_after=score_after,
                    created_at=now,
                )
                return IngestScoreEventOutput(
                    event_id=same_sequence_event.event_id,
                    idempotent_replay=True,
                    sequence=request.sequence,
                    score_before=score_before,
                    score_after=score_after,
                    received_at=now,
                )
            raise ValidationError(
                "Sequence already exists for this session with a different score event payload"
            )

        score_before = running_target_score(
            events=judge_events,
            side=side,
            round_number=request.round_number,
            target=target,
            bounds=bounds,
            before_sequence=request.sequence,
        )
        score_after = apply_delta(score_before, delta.value, bounds)
        now = self._clock.now()

        event = ScoreEvent(
            id=self._id_generator.new("score"),
            idempotency_key=request.idempotency_key,
            event_id=request.event_id,
            session_id=request.session_id,
            station_id=request.station_id,
            match_id=match.id,
            round_number=request.round_number,
            athlete_side=side,
            score_delta=delta.value,
            score_before=score_before,
            score_after=score_after,
            occurred_at=request.occurred_at,
            sequence=request.sequence,
            judge_name=request.judge_name,
            received_at=now,
            processed_at=now,
            score_target=target,
        )
        self._score_event_repository.save(event)
        # A judge that joined the station after the start counts from its first score event of the match.
        if match.add_judge(session.scorecard_key):
            self._match_repository.save_match(match)

        self._save_idempotent_response(
            idempotency_key=request.idempotency_key,
            event_id=request.event_id,
            sequence=request.sequence,
            score_before=score_before,
            score_after=score_after,
            created_at=now,
        )

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="score_event",
                action="ingest",
                subject_id=event.id,
                actor=request.judge_name,
                details=f"match_id={match.id};sequence={request.sequence}",
                occurred_at=now,
            )
        )

        await self._realtime.publish_to_station(
            request.station_id,
            "match_updated",
            {
                "matchId": match.id,
                "sessionId": request.session_id,
                "judgeName": request.judge_name,
                "roundNumber": request.round_number,
                "sequence": request.sequence,
                "athleteSide": request.athlete_side,
                "scoreTarget": target.value,
                "scoreAfter": str(score_after),
            },
        )

        return IngestScoreEventOutput(
            event_id=request.event_id,
            idempotent_replay=False,
            sequence=request.sequence,
            score_before=score_before,
            score_after=score_after,
            received_at=now,
        )

    def _save_idempotent_response(
        self,
        *,
        idempotency_key: str,
        event_id: str,
        sequence: int,
        score_before: Decimal,
        score_after: Decimal,
        created_at,
    ) -> None:
        response = {
            "event_id": event_id,
            "sequence": sequence,
            "score_before": str(score_before),
            "score_after": str(score_after),
        }
        self._idempotency_repository.save(
            IdempotencyRecord(
                id=self._id_generator.new("idem"),
                key=idempotency_key,
                operation="score_event_ingestion",
                response_payload=to_json_payload(response),
                created_at=created_at,
            )
        )
