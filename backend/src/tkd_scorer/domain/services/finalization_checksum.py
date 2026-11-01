"""Canonical finalize payload shared by the judge app and the server.

Both sides build the same JSON string from one judge's scorecard and hash it with SHA-256 (hex):

- keys sorted, compact separators (",", ":"), non-ASCII characters kept as UTF-8 (like JSON.stringify);
- scores as strings with exactly 2 decimals ("8.85"); counters and round numbers as JSON integers;
- rounds sorted by roundNumber.

The app counterpart is buildFinalizeChecksumPayload in judge-app/src/domain/services/checksum.ts.
A shared test vector (tests/unit/test_finalization_checksum.py and judge-app tests/unit/checksumAndFinalization.test.ts)
keeps both implementations in sync.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal

from tkd_scorer.domain.services.judge_scorecard import JudgeScorecard, RoundScore, round2


def format_score(value: Decimal) -> str:
    return str(round2(value))


def build_finalize_checksum_payload(
    *,
    match_id: str,
    session_id: str,
    station_id: str,
    judge_name: str,
    total_events: int,
    last_sequence: int,
    final_score_red: Decimal,
    final_score_blue: Decimal,
    rounds: Iterable[RoundScore],
) -> dict:
    return {
        "matchId": match_id,
        "sessionId": session_id,
        "stationId": station_id,
        "judgeName": judge_name,
        "totalEvents": int(total_events),
        "lastSequence": int(last_sequence),
        "finalScoreRed": format_score(final_score_red),
        "finalScoreBlue": format_score(final_score_blue),
        "rounds": [
            {
                "roundNumber": int(item.round_number),
                "techniqueRed": format_score(item.technique_red),
                "presentationRed": format_score(item.presentation_red),
                "techniqueBlue": format_score(item.technique_blue),
                "presentationBlue": format_score(item.presentation_blue),
            }
            for item in sorted(rounds, key=lambda value: value.round_number)
        ],
    }


def scorecard_checksum_payload(*, match_id: str, station_id: str, scorecard: JudgeScorecard) -> dict:
    return build_finalize_checksum_payload(
        match_id=match_id,
        session_id=scorecard.session_id,
        station_id=station_id,
        judge_name=scorecard.judge_name,
        total_events=scorecard.total_events,
        last_sequence=scorecard.last_sequence,
        final_score_red=scorecard.final_score_red,
        final_score_blue=scorecard.final_score_blue,
        rounds=scorecard.rounds,
    )


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
