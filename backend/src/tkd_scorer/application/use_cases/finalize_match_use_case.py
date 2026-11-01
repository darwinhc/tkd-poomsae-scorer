from dataclasses import asdict
from decimal import Decimal, InvalidOperation

from tkd_scorer.application.dto.match_dto import FinalizeMatchInput, FinalizeMatchOutput
from tkd_scorer.application.use_cases._datetime_format import to_iso_utc_z
from tkd_scorer.application.use_cases._helpers import from_json_payload, to_json_payload
from tkd_scorer.application.use_cases._match_scoring import (
    ScorecardKeys,
    close_match_when_complete,
    latest_finalizations_by_judge,
)
from tkd_scorer.domain.entities.audit import AuditEvent
from tkd_scorer.domain.entities.common import MatchStatus
from tkd_scorer.domain.entities.match import Match
from tkd_scorer.domain.entities.score_event import FinalizationRecord
from tkd_scorer.domain.exceptions.errors import UnauthorizedError, ValidationError
from tkd_scorer.domain.services.finalization_checksum import (
    format_score,
    scorecard_checksum_payload,
)
from tkd_scorer.domain.services.judge_scorecard import JudgeScorecard, build_judge_scorecard, round2
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort
from tkd_scorer.ports.realtime.realtime_port import RealtimePort
from tkd_scorer.ports.repositories.audit_repository_port import AuditRepositoryPort
from tkd_scorer.ports.repositories.finalization_repository_port import FinalizationRepositoryPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.score_event_repository_port import ScoreEventRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort
from tkd_scorer.ports.repositories.station_repository_port import StationRepositoryPort
from tkd_scorer.ports.services.checksum_service_port import ChecksumServicePort

_CHECKSUM_MODE = "canonical_scorecard"
_ROUND_PARTS = ("techniqueRed", "presentationRed", "techniqueBlue", "presentationBlue")


class FinalizeMatchUseCase:
    """Finalizes the scorecard of the calling judge on the shared match of the station.

    The shared match stays in progress until every counted judge (match.judges_required: the judges of the
    start plus the ones that joined and scored, minus the ones removed by the operator) has finalized; it is
    then closed as FINISHED, or FINALIZATION_PENDING when any judge scorecard did not reconcile with the
    server. A judge that replaced its session finalizes its single scorecard (events of all its sessions).
    """

    def __init__(
        self,
        *,
        finalization_repository: FinalizationRepositoryPort,
        match_repository: MatchRepositoryPort,
        score_event_repository: ScoreEventRepositoryPort,
        session_repository: SessionRepositoryPort,
        station_repository: StationRepositoryPort,
        checksum_service: ChecksumServicePort,
        audit_repository: AuditRepositoryPort,
        realtime: RealtimePort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
        presentation_category_start_score: Decimal = Decimal("2.0"),
    ) -> None:
        self._finalization_repository = finalization_repository
        self._match_repository = match_repository
        self._score_event_repository = score_event_repository
        self._session_repository = session_repository
        self._station_repository = station_repository
        self._checksum_service = checksum_service
        self._audit_repository = audit_repository
        self._realtime = realtime
        self._clock = clock
        self._id_generator = id_generator
        self._presentation_category_start_score = Decimal(str(presentation_category_start_score))

    async def execute(self, request: FinalizeMatchInput) -> FinalizeMatchOutput:
        existing = self._finalization_repository.get_by_idempotency_key(request.idempotency_key)
        if existing is not None:
            return self._replay(existing)

        session = self._session_repository.get_by_id(request.session_id)
        if session is None:
            raise UnauthorizedError("Session not found")
        if session.station_id != request.station_id:
            raise UnauthorizedError("Session/station mismatch")
        if session.judge_name != request.judge_name:
            raise UnauthorizedError("Judge mismatch")

        match_id = request.match_id.strip()
        if not match_id:
            raise ValidationError("matchId is required")
        match = self._match_repository.get_match(match_id)
        if match is None:
            raise ValidationError("matchId must reference an existing backend match")
        if match.station_id != request.station_id:
            raise UnauthorizedError("Match/station mismatch")
        if match.status not in (MatchStatus.IN_PROGRESS, MatchStatus.FINALIZATION_PENDING, MatchStatus.FINISHED):
            raise ValidationError("Match cannot be finalized from current status")

        keys = ScorecardKeys(self._session_repository)
        keys.remember(session)
        judge_key = session.scorecard_key
        # A judge finalizes once per match: a second finalization (retry, new idempotency key, or from the
        # session that replaced it) replays the first.
        previous = self._judge_finalization(match_id=match.id, judge_key=judge_key, keys=keys)
        if previous is not None:
            return self._replay(previous)
        if not request.session_active:
            raise UnauthorizedError("Session is not active")

        reported_rounds = self._normalize_rounds_summary(request.rounds_summary)
        match_events = self._score_event_repository.list_for_match(match.id)
        chain = keys.chain(judge_key, [*(item.session_id for item in match_events), request.session_id])
        judge_events = [item for item in match_events if item.session_id in chain]
        round_numbers = sorted({item["roundNumber"] for item in reported_rounds} | {e.round_number for e in judge_events})
        scorecard = build_judge_scorecard(
            session_id=request.session_id,
            judge_name=request.judge_name,
            events=judge_events,
            round_numbers=round_numbers,
            technique_start=match.starting_score,
            presentation_category_start=self._presentation_category_start_score,
            session_ids=chain,
        )
        server_rounds = self._scorecard_rounds_summary(scorecard)
        expected_payload = scorecard_checksum_payload(
            match_id=match.id,
            station_id=request.station_id,
            scorecard=scorecard,
        )
        checksum_verified = self._checksum_service.verify(expected_payload, request.checksum)
        checksum_mode = _CHECKSUM_MODE if checksum_verified else "mismatch"

        reported_final_red = self._normalize_score(request.final_score_left)
        reported_final_blue = self._normalize_score(request.final_score_right)
        notes: list[str] = []
        if request.total_events != scorecard.total_events:
            notes.append("totalEvents mismatch")
        if request.last_sequence != scorecard.last_sequence:
            notes.append("lastSequence mismatch")
        if reported_final_red != scorecard.final_score_red:
            notes.append("finalScoreRed mismatch")
        if reported_final_blue != scorecard.final_score_blue:
            notes.append("finalScoreBlue mismatch")
        if reported_rounds and not self._rounds_match(reported_rounds, server_rounds):
            notes.append("roundsSummary mismatch")
        if not checksum_verified:
            notes.append("checksum mismatch")
        reconciled = not notes
        judge_status = MatchStatus.FINISHED.value if reconciled else MatchStatus.FINALIZATION_PENDING.value
        note_text = "; ".join(notes) if notes else "reconciled"

        now = self._clock.now()
        record = FinalizationRecord(
            id=self._id_generator.new("fin"),
            idempotency_key=request.idempotency_key,
            session_id=request.session_id,
            station_id=request.station_id,
            match_id=match.id,
            checksum=request.checksum,
            status=judge_status,
            reconciliation_notes=note_text,
            created_at=now,
            round_numbers=tuple(round_numbers),
        )
        judges_finalized, match_closed = self._close_match_when_complete(
            match=match, new_record=record, keys=keys, now=now
        )

        output = FinalizeMatchOutput(
            match_id=match.id,
            status=judge_status,
            reconciled=reconciled,
            notes=note_text,
            idempotent_replay=False,
            checksum_verified=checksum_verified,
            checksum_mode=checksum_mode,
            reported_final_score_left=reported_final_red,
            reported_final_score_right=reported_final_blue,
            server_final_score_left=scorecard.final_score_red,
            server_final_score_right=scorecard.final_score_blue,
            match_status=match.status.value,
            judges_finalized=judges_finalized,
            judges_required=match.judges_required,
        )
        record.response_payload = to_json_payload(self._output_as_payload(output))
        self._finalization_repository.save(record)

        if reconciled:
            # Release the judge that just finalized, as in single-judge mode; the other judges keep scoring.
            self._session_repository.revoke(request.session_id)
            station = self._station_repository.get_by_id(request.station_id)
            if station is not None:
                active_sessions = self._session_repository.list_active_by_station(request.station_id)
                if active_sessions:
                    station.mark_connected(active_sessions[0].id)
                else:
                    station.mark_disconnected()
                self._station_repository.save(station)

        self._audit_repository.save(
            AuditEvent(
                id=self._id_generator.new("audit"),
                category="finalization",
                action="finalize_match",
                subject_id=match.id,
                actor=request.judge_name,
                details=to_json_payload(
                    {
                        "requestedMatchId": request.match_id,
                        "resolvedMatchId": match.id,
                        "sessionId": request.session_id,
                        "status": judge_status,
                        "matchStatus": match.status.value,
                        "reconciled": reconciled,
                        "notes": notes,
                        "checksumMode": checksum_mode,
                        "checksumVerified": checksum_verified,
                        "reportedFinalScoreRed": str(reported_final_red),
                        "reportedFinalScoreBlue": str(reported_final_blue),
                        "serverFinalScoreRed": str(scorecard.final_score_red),
                        "serverFinalScoreBlue": str(scorecard.final_score_blue),
                        "reportedRoundsSummary": reported_rounds,
                        "serverRoundsSummary": server_rounds,
                        "judgesFinalized": judges_finalized,
                        "judgesRequired": match.judges_required,
                    }
                ),
                occurred_at=now,
            )
        )

        await self._realtime.publish_to_station(
            request.station_id,
            "match_updated",
            {
                "matchId": match.id,
                # Shared match status: judges that did not finalize yet keep it as their active match.
                "status": match.status.value,
                "sessionId": request.session_id,
                "judgeName": request.judge_name,
                "judgeStatus": judge_status,
                "reconciled": reconciled,
                "notes": notes,
                "checksumMode": checksum_mode,
                "checksumVerified": checksum_verified,
                "judgesFinalized": judges_finalized,
                "judgesRequired": match.judges_required,
            },
        )

        if match_closed and match.status == MatchStatus.FINISHED:
            await self._realtime.publish_to_station(
                request.station_id,
                "active_match_state",
                {
                    "hasActiveMatch": False,
                    "matchId": match.id,
                    "competitorRedName": None,
                    "competitorBlueName": None,
                    "issuedAt": to_iso_utc_z(now),
                },
            )

        if reconciled:
            await self._realtime.publish_to_session(
                request.session_id,
                "session_revoked",
                {
                    "sessionId": request.session_id,
                    "reason": "match_finalized",
                },
            )

        return output

    def _close_match_when_complete(
        self, *, match: Match, new_record: FinalizationRecord, keys: ScorecardKeys, now
    ) -> tuple[int, bool]:
        """Counts distinct finalized judges (including new_record) and closes the shared match when complete."""
        latest_by_judge = latest_finalizations_by_judge(
            match=match,
            finalizations=[*self._finalization_repository.list_for_match(match.id), new_record],
            keys=keys,
        )
        closed = close_match_when_complete(match=match, latest_by_judge=latest_by_judge, now=now)
        if closed:
            self._match_repository.save_match(match)
        return len(latest_by_judge), closed

    def _judge_finalization(self, *, match_id: str, judge_key: str, keys: ScorecardKeys) -> FinalizationRecord | None:
        for item in self._finalization_repository.list_for_match(match_id):
            if keys.key(item.session_id) == judge_key:
                return item
        return None

    def _replay(self, record: FinalizationRecord) -> FinalizeMatchOutput:
        payload = self._safe_payload(record.response_payload)
        if not payload:
            return FinalizeMatchOutput(
                match_id=record.match_id,
                status=record.status,
                reconciled=record.status == MatchStatus.FINISHED.value,
                notes=record.reconciliation_notes,
                idempotent_replay=True,
            )
        return FinalizeMatchOutput(
            match_id=str(payload.get("match_id") or record.match_id),
            status=str(payload.get("status") or record.status),
            reconciled=bool(payload.get("reconciled")),
            notes=str(payload.get("notes") or record.reconciliation_notes),
            idempotent_replay=True,
            checksum_verified=bool(payload.get("checksum_verified")),
            checksum_mode=str(payload.get("checksum_mode") or "mismatch"),
            reported_final_score_left=self._optional_decimal(payload.get("reported_final_score_left")),
            reported_final_score_right=self._optional_decimal(payload.get("reported_final_score_right")),
            server_final_score_left=self._optional_decimal(payload.get("server_final_score_left")),
            server_final_score_right=self._optional_decimal(payload.get("server_final_score_right")),
            match_status=payload.get("match_status") if isinstance(payload.get("match_status"), str) else None,
            judges_finalized=int(payload.get("judges_finalized") or 0),
            judges_required=int(payload.get("judges_required") or 1),
        )

    @staticmethod
    def _output_as_payload(output: FinalizeMatchOutput) -> dict:
        payload = asdict(output)
        payload.pop("idempotent_replay", None)
        return {key: (str(value) if isinstance(value, Decimal) else value) for key, value in payload.items()}

    @staticmethod
    def _scorecard_rounds_summary(scorecard: JudgeScorecard) -> list[dict]:
        return [
            {
                "roundNumber": item.round_number,
                "techniqueRed": format_score(item.technique_red),
                "presentationRed": format_score(item.presentation_red),
                "techniqueBlue": format_score(item.technique_blue),
                "presentationBlue": format_score(item.presentation_blue),
                "finalScoreRed": format_score(item.technique_red + item.presentation_red),
                "finalScoreBlue": format_score(item.technique_blue + item.presentation_blue),
            }
            for item in scorecard.rounds
        ]

    @staticmethod
    def _rounds_match(reported: list[dict], server: list[dict]) -> bool:
        server_by_round = {item["roundNumber"]: item for item in server}
        if set(server_by_round) != {item["roundNumber"] for item in reported}:
            return False
        for item in reported:
            expected = server_by_round[item["roundNumber"]]
            parts = [key for key in _ROUND_PARTS if key in item]
            # Older apps only report the round totals per side.
            keys = parts if parts else ["finalScoreRed", "finalScoreBlue"]
            for key in keys:
                if item.get(key) != expected.get(key):
                    return False
        return True

    def _normalize_rounds_summary(self, rounds_summary: list[dict] | None) -> list[dict]:
        if not rounds_summary:
            return []

        by_round: dict[int, dict] = {}
        for item in rounds_summary:
            if not isinstance(item, dict):
                continue
            round_number = self._pick_int(item, ("roundNumber", "round", "round_number"))
            if round_number is None or round_number <= 0:
                continue
            normalized: dict = {"roundNumber": round_number}
            for key in _ROUND_PARTS:
                value = self._pick_decimal(item, (key,))
                if value is not None:
                    normalized[key] = format_score(value)
            red_score = self._pick_decimal(
                item,
                ("finalScoreRed", "finalScoreLeft", "redScore", "red_score", "red"),
            )
            blue_score = self._pick_decimal(
                item,
                ("finalScoreBlue", "finalScoreRight", "blueScore", "blue_score", "blue"),
            )
            if red_score is not None:
                normalized["finalScoreRed"] = format_score(red_score)
            if blue_score is not None:
                normalized["finalScoreBlue"] = format_score(blue_score)
            by_round[round_number] = normalized
        return [by_round[key] for key in sorted(by_round)]

    @staticmethod
    def _normalize_score(value: Decimal) -> Decimal:
        return round2(Decimal(str(value)))

    @staticmethod
    def _optional_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _safe_payload(raw: str) -> dict:
        if not raw:
            return {}
        try:
            value = from_json_payload(raw)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _pick_int(value: dict, keys: tuple[str, ...]) -> int | None:
        for key in keys:
            raw = value.get(key)
            if isinstance(raw, bool):
                continue
            if isinstance(raw, int):
                return raw
            if isinstance(raw, str) and raw.strip().isdigit():
                return int(raw.strip())
        return None

    @staticmethod
    def _pick_decimal(value: dict, keys: tuple[str, ...]) -> Decimal | None:
        for key in keys:
            raw = value.get(key)
            if raw is None or isinstance(raw, bool):
                continue
            try:
                return Decimal(str(raw))
            except (InvalidOperation, ValueError):
                continue
        return None
