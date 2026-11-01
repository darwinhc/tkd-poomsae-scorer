from __future__ import annotations

import logging

from tkd_scorer.application.dto.realtime_dto import (
    JudgeMatchCompletedSignalInput,
    JudgeRoundCompletedSignalInput,
    JudgeSignalOutput,
)
from tkd_scorer.application.use_cases._datetime_format import to_iso_utc_z
from tkd_scorer.application.use_cases._helpers import to_json_payload
from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import MatchStatus
from tkd_scorer.domain.exceptions.errors import NotFoundError, UnauthorizedError, ValidationError
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort
from tkd_scorer.ports.realtime.realtime_port import RealtimePort
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort


class HandleJudgeWsSignalsUseCase:
    def __init__(
        self,
        *,
        session_repository: SessionRepositoryPort,
        match_repository: MatchRepositoryPort,
        audit_repository: AuditRepositoryPort,
        realtime: RealtimePort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._session_repository = session_repository
        self._match_repository = match_repository
        self._audit_repository = audit_repository
        self._realtime = realtime
        self._clock = clock
        self._id_generator = id_generator
        self._logger = logging.getLogger("tkd_scorer.use_case.ws_judge_signal")

    async def handle_round_completed(self, request: JudgeRoundCompletedSignalInput) -> JudgeSignalOutput:
        if request.round_number <= 0:
            raise ValidationError("roundNumber must be greater than zero")
        self._validate_session(
            session_id=request.session_id,
            station_id=request.station_id,
            judge_name=request.judge_name,
            device_id=request.device_id,
        )
        match = self._resolve_match(
            requested_match_id=request.match_id,
            station_id=request.station_id,
            session_id=request.session_id,
            judge_name=request.judge_name,
        )
        now = self._clock.now()
        finished_at = request.finished_at or now
        payload = {
            "matchId": match.id,
            "roundNumber": request.round_number,
            "sessionId": request.session_id,
            "stationId": request.station_id,
            "judgeName": request.judge_name,
            "deviceId": request.device_id,
            "finishedAt": to_iso_utc_z(finished_at),
        }
        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="ws_signal",
                action="judge_round_completed",
                subject_id=match.id,
                actor=request.judge_name,
                details=to_json_payload(payload),
                occurred_at=now,
            )
        )
        await self._realtime.publish_to_station(
            request.station_id,
            "match_updated",
            {
                "updateType": "judge_round_completed",
                **payload,
                "acceptedAt": to_iso_utc_z(now),
            },
        )
        return JudgeSignalOutput(
            signal_type="judge_round_completed",
            match_id=match.id,
            station_id=request.station_id,
            session_id=request.session_id,
            judge_name=request.judge_name,
            accepted_at=now,
        )

    async def handle_match_completed(self, request: JudgeMatchCompletedSignalInput) -> JudgeSignalOutput:
        if request.final_round <= 0:
            raise ValidationError("finalRound must be greater than zero")
        if not request.checksum.strip():
            raise ValidationError("checksum is required")
        self._validate_session(
            session_id=request.session_id,
            station_id=request.station_id,
            judge_name=request.judge_name,
            device_id=request.device_id,
        )
        match = self._resolve_match(
            requested_match_id=request.match_id,
            station_id=request.station_id,
            session_id=request.session_id,
            judge_name=request.judge_name,
        )
        now = self._clock.now()
        finished_at = request.finished_at or now
        payload = {
            "matchId": match.id,
            "finalRound": request.final_round,
            "checksum": request.checksum,
            "sessionId": request.session_id,
            "stationId": request.station_id,
            "judgeName": request.judge_name,
            "deviceId": request.device_id,
            "finishedAt": to_iso_utc_z(finished_at),
        }
        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="ws_signal",
                action="judge_match_completed",
                subject_id=match.id,
                actor=request.judge_name,
                details=to_json_payload(payload),
                occurred_at=now,
            )
        )
        await self._realtime.publish_to_station(
            request.station_id,
            "match_updated",
            {
                "updateType": "judge_match_completed",
                **payload,
                "acceptedAt": to_iso_utc_z(now),
            },
        )
        return JudgeSignalOutput(
            signal_type="judge_match_completed",
            match_id=match.id,
            station_id=request.station_id,
            session_id=request.session_id,
            judge_name=request.judge_name,
            accepted_at=now,
        )

    def _validate_session(self, *, session_id: str, station_id: str, judge_name: str, device_id: str | None) -> None:
        session = self._session_repository.get_by_id(session_id)
        if session is None:
            raise UnauthorizedError("Session not found")
        if session.station_id != station_id:
            raise UnauthorizedError("Session/station mismatch")
        if session.judge_name != judge_name:
            raise UnauthorizedError("Judge mismatch")
        if device_id and session.device_id != device_id:
            raise UnauthorizedError("Device mismatch")

    def _resolve_match(
        self,
        *,
        requested_match_id: str,
        station_id: str,
        session_id: str,
        judge_name: str,
    ):
        requested = self._match_repository.get_match(requested_match_id)
        if requested is not None and requested.station_id == station_id:
            return requested
        if requested is not None and requested.station_id != station_id:
            raise UnauthorizedError("Match/station mismatch")

        candidates = self._match_repository.list_recent(
            limit=200,
            statuses=[
                MatchStatus.IN_PROGRESS.value,
                MatchStatus.FINALIZATION_PENDING.value,
                MatchStatus.FINISHED.value,
            ],
        )
        station_candidates = [item for item in candidates if item.station_id == station_id]
        if not station_candidates:
            raise NotFoundError("Match not found")

        by_session = [item for item in station_candidates if item.session_id == session_id]
        if len(by_session) == 1:
            self._logger.info(
                "ws_signal_match_fallback_resolved_by_session requested_match_id=%s resolved_match_id=%s station_id=%s session_id=%s",
                requested_match_id,
                by_session[0].id,
                station_id,
                session_id,
            )
            return by_session[0]

        by_judge = [item for item in station_candidates if item.judge_name == judge_name]
        if len(by_judge) == 1:
            self._logger.info(
                "ws_signal_match_fallback_resolved_by_judge requested_match_id=%s resolved_match_id=%s station_id=%s judge_name=%s",
                requested_match_id,
                by_judge[0].id,
                station_id,
                judge_name,
            )
            return by_judge[0]

        if len(station_candidates) == 1:
            self._logger.info(
                "ws_signal_match_fallback_resolved_single_station_match requested_match_id=%s resolved_match_id=%s station_id=%s",
                requested_match_id,
                station_candidates[0].id,
                station_id,
            )
            return station_candidates[0]

        self._logger.warning(
            "ws_signal_match_fallback_failed requested_match_id=%s station_id=%s session_id=%s judge_name=%s station_candidates=%s by_session=%s by_judge=%s",
            requested_match_id,
            station_id,
            session_id,
            judge_name,
            len(station_candidates),
            len(by_session),
            len(by_judge),
        )
        raise NotFoundError("Match not found")
