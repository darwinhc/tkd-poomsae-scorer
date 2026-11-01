from __future__ import annotations

from tkd_scorer.application.dto.session_dto import KickJudgeSessionOutput
from tkd_scorer.application.use_cases._datetime_format import to_iso_utc_z
from tkd_scorer.application.use_cases._helpers import to_json_payload
from tkd_scorer.application.use_cases._match_scoring import (
    ScorecardKeys,
    close_match_when_complete,
    latest_finalizations_by_judge,
)
from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import MatchStatus, SessionStatus
from tkd_scorer.domain.entities.device_session import DeviceSession
from tkd_scorer.domain.entities.match import Match
from tkd_scorer.domain.exceptions.errors import NotFoundError, ValidationError
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort
from tkd_scorer.ports.realtime.realtime_port import RealtimePort
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.finalization_repository_port import FinalizationRepositoryPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort
from tkd_scorer.ports.repositories.station_repository_port import StationRepositoryPort


class KickJudgeSessionUseCase:
    def __init__(
        self,
        *,
        session_repository: SessionRepositoryPort,
        station_repository: StationRepositoryPort,
        audit_repository: AuditRepositoryPort,
        realtime: RealtimePort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
        match_repository: MatchRepositoryPort | None = None,
        finalization_repository: FinalizationRepositoryPort | None = None,
        match_lookup_limit: int = 50,
    ) -> None:
        self._match_repository = match_repository
        self._finalization_repository = finalization_repository
        self._match_lookup_limit = max(1, int(match_lookup_limit))
        self._session_repository = session_repository
        self._station_repository = station_repository
        self._audit_repository = audit_repository
        self._realtime = realtime
        self._clock = clock
        self._id_generator = id_generator

    async def execute(
        self,
        *,
        station_id: str,
        session_id: str,
        reason: str,
        actor: str,
    ) -> KickJudgeSessionOutput:
        session = self._session_repository.get_by_id(session_id)
        if session is None:
            raise NotFoundError("Session not found")
        if session.station_id != station_id:
            raise ValidationError("Session/station mismatch")

        now = self._clock.now()
        normalized_reason = reason.strip() or "operator_replaced"

        was_active = session.status == SessionStatus.ACTIVE
        if was_active:
            self._session_repository.revoke(session_id)
        closed_matches = self._remove_from_live_matches(session, now=now) if was_active else []

        remaining = self._session_repository.list_active_by_station(station_id)
        station = self._station_repository.get_by_id(station_id)
        if station is not None:
            if remaining:
                station.mark_connected(remaining[0].id)
            else:
                station.mark_disconnected()
            self._station_repository.save(station)

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="session",
                action="kick",
                subject_id=session_id,
                actor=actor,
                details=to_json_payload(
                    {
                        "stationId": station_id,
                        "judgeName": session.judge_name,
                        "deviceId": session.device_id,
                        "reason": normalized_reason,
                    }
                ),
                occurred_at=now,
            )
        )

        payload = {
            "sessionId": session_id,
            "stationId": station_id,
            "reason": normalized_reason,
            "issuedAt": to_iso_utc_z(now),
        }
        await self._realtime.publish_to_session(session_id, "judge_kicked", payload)
        await self._realtime.publish_to_session(
            session_id,
            "session_revoked",
            {
                "sessionId": session_id,
                "reason": normalized_reason,
            },
        )

        for match in closed_matches:
            await self._realtime.publish_to_station(
                station_id,
                "match_updated",
                {"matchId": match.id, "status": match.status.value, "judgesRequired": match.judges_required},
            )
            if match.status == MatchStatus.FINISHED:
                await self._realtime.publish_to_station(
                    station_id,
                    "active_match_state",
                    {
                        "hasActiveMatch": False,
                        "matchId": match.id,
                        "competitorRedName": None,
                        "competitorBlueName": None,
                        "issuedAt": to_iso_utc_z(now),
                    },
                )

        return KickJudgeSessionOutput(
            station_id=station_id,
            session_id=session_id,
            judge_name=session.judge_name,
            status=SessionStatus.REVOKED.value,
            remaining_active_sessions=len(remaining),
            message="Judge removed. Reconnect with QR + PIN.",
        )

    def _remove_from_live_matches(self, session: DeviceSession, *, now) -> list[Match]:
        """The removed judge stops counting in the running shared match(es) it has not finalized.

        Its partial scorecard is left out of the consolidation; when every remaining judge has already
        finalized, the match closes as on a normal finalization. Returns the matches that closed.
        """
        if self._match_repository is None:
            return []
        keys = ScorecardKeys(self._session_repository)
        keys.remember(session)
        judge_key = session.scorecard_key
        root = keys.session(judge_key) or session
        closed: list[Match] = []
        for match in self._match_repository.list_recent(
            limit=self._match_lookup_limit,
            statuses=[MatchStatus.IN_PROGRESS.value],
        ):
            if match.station_id != session.station_id:
                continue
            if not match.counts_judge(judge_key, first_connected_at=root.created_at):
                continue
            finalizations = (
                self._finalization_repository.list_for_match(match.id) if self._finalization_repository else []
            )
            if any(keys.key(item.session_id) == judge_key for item in finalizations):
                continue
            match.remove_judge(judge_key)
            latest = latest_finalizations_by_judge(match=match, finalizations=finalizations, keys=keys)
            if latest and close_match_when_complete(match=match, latest_by_judge=latest, now=now):
                closed.append(match)
            self._match_repository.save_match(match)
        return closed
