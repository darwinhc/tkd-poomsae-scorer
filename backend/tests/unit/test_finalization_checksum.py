import hashlib
from decimal import Decimal

from tkd_scorer.adapters.checksum.sha256_checksum_service import Sha256ChecksumService
from tkd_scorer.domain.services.finalization_checksum import (
    build_finalize_checksum_payload,
    canonical_json,
    format_score,
)
from tkd_scorer.domain.services.judge_scorecard import RoundScore

# Shared test vector: judge-app/tests/unit/checksumAndFinalization.test.ts builds the same payload with
# buildFinalizeChecksumPayload and must produce exactly this string and digest.
SHARED_VECTOR_CANONICAL = (
    '{"finalScoreBlue":"9.75","finalScoreRed":"9.30","judgeName":"Judge É","lastSequence":9,'
    '"matchId":"match-vector-1","rounds":[{"presentationBlue":"6.00","presentationRed":"5.80","roundNumber":1,'
    '"techniqueBlue":"3.90","techniqueRed":"3.60"},{"presentationBlue":"5.90","presentationRed":"5.70",'
    '"roundNumber":2,"techniqueBlue":"3.70","techniqueRed":"3.50"}],"sessionId":"session-vector-1",'
    '"stationId":"station-01","totalEvents":7}'
)
SHARED_VECTOR_SHA256 = "3835fc5400b88b7fdb67a709fbf3d456709fc862247d3fef7a64ec04bf5c4526"


def _shared_vector_payload() -> dict:
    return build_finalize_checksum_payload(
        match_id="match-vector-1",
        session_id="session-vector-1",
        station_id="station-01",
        judge_name="Judge É",
        total_events=7,
        last_sequence=9,
        final_score_red=Decimal("9.3"),
        final_score_blue=Decimal("9.75"),
        # Unsorted on purpose: the payload sorts rounds by number.
        rounds=[
            RoundScore(
                round_number=2,
                technique_red=Decimal("3.5"),
                presentation_red=Decimal("5.7"),
                technique_blue=Decimal("3.7"),
                presentation_blue=Decimal("5.9"),
            ),
            RoundScore(
                round_number=1,
                technique_red=Decimal("3.6"),
                presentation_red=Decimal("5.8"),
                technique_blue=Decimal("3.9"),
                presentation_blue=Decimal("6"),
            ),
        ],
    )


def test_shared_vector_canonical_string_matches_the_judge_app() -> None:
    assert canonical_json(_shared_vector_payload()) == SHARED_VECTOR_CANONICAL


def test_shared_vector_sha256_matches_the_judge_app() -> None:
    payload = _shared_vector_payload()
    assert hashlib.sha256(SHARED_VECTOR_CANONICAL.encode("utf-8")).hexdigest() == SHARED_VECTOR_SHA256
    assert Sha256ChecksumService().compute(payload) == SHARED_VECTOR_SHA256
    assert Sha256ChecksumService().verify(payload, SHARED_VECTOR_SHA256) is True


def test_scores_are_serialized_with_exactly_two_decimals_half_up() -> None:
    assert format_score(Decimal("8.85")) == "8.85"
    assert format_score(Decimal("4")) == "4.00"
    assert format_score(Decimal("9.465")) == "9.47"
    assert format_score(Decimal("0")) == "0.00"
