"""Per-judge scorecard built from the judge's own score events.

Mirrors the judge app (judge-app/src/domain/services/scoreCalculator.ts and matchService.ts) so both sides
compute the same numbers:

- Technique (accuracy) starts at the technique start score (default 4.0) and is kept in [0, start].
- Each presentation category (speed and power, rhythm and tempo, energy and expression) starts at the
  category start score (default 2.0) and is kept in [0, 2.0]; presentation is the sum of the three.
- Deltas are applied in sequence order, clamping after each one like the app does when it records them.
- A judge that replaced its session (new device or reconnection) keeps one scorecard: the events of its
  sessions are applied session after session (in connection order), each session in sequence order.
- A round with no events keeps the start values.
- The judge's final score is the 2-decimal average of technique plus the 2-decimal average of presentation
  over the judge's rounds (the app's summary does the same).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from tkd_scorer.domain.entities.common import AthleteSide, ScoreTarget
from tkd_scorer.domain.entities.score_event import ScoreEvent
from tkd_scorer.domain.exceptions.errors import ValidationError

PRESENTATION_CATEGORY_MAX_SCORE = Decimal("2.0")
PRESENTATION_TARGETS: tuple[ScoreTarget, ...] = (
    ScoreTarget.PRESENTATION_SPEED_POWER,
    ScoreTarget.PRESENTATION_RHYTHM_TEMPO,
    ScoreTarget.PRESENTATION_ENERGY_EXPRESSION,
)

_SCORE_STEP = Decimal("0.1")
_TWO_PLACES = Decimal("0.01")
_ZERO = Decimal("0")


def round2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def parse_score_target(value: str | None) -> ScoreTarget:
    """Missing targets are technique deductions (events sent before presentation existed)."""
    if value is None or not str(value).strip():
        return ScoreTarget.TECHNIQUE
    try:
        return ScoreTarget(str(value).strip().upper())
    except ValueError as exc:
        raise ValidationError("Invalid scoreTarget") from exc


@dataclass(frozen=True)
class TargetBounds:
    start: Decimal
    maximum: Decimal


def target_bounds(
    target: ScoreTarget,
    *,
    technique_start: Decimal,
    presentation_category_start: Decimal,
) -> TargetBounds:
    if target == ScoreTarget.TECHNIQUE:
        return TargetBounds(start=Decimal(technique_start), maximum=Decimal(technique_start))
    return TargetBounds(start=Decimal(presentation_category_start), maximum=PRESENTATION_CATEGORY_MAX_SCORE)


def running_target_score(
    *,
    events: Iterable[ScoreEvent],
    side: AthleteSide,
    round_number: int,
    target: ScoreTarget,
    bounds: TargetBounds,
    before_sequence: int | None = None,
    sort_key: Callable[[ScoreEvent], object] | None = None,
) -> Decimal:
    """Value of one target (one judge, round and side) after applying its deltas in sequence order."""
    relevant = [
        event
        for event in events
        if event.athlete_side == side
        and event.round_number == round_number
        and event.score_target == target
        and (before_sequence is None or event.sequence < before_sequence)
    ]
    total = _clamp(bounds.start, bounds.maximum)
    for event in sorted(relevant, key=sort_key or (lambda item: item.sequence)):
        total = _clamp(total + event.score_delta, bounds.maximum)
    return total.quantize(_SCORE_STEP)


def apply_delta(value: Decimal, delta: Decimal, bounds: TargetBounds) -> Decimal:
    return _clamp(value + delta, bounds.maximum).quantize(_SCORE_STEP)


@dataclass(frozen=True)
class RoundScore:
    round_number: int
    technique_red: Decimal
    presentation_red: Decimal
    technique_blue: Decimal
    presentation_blue: Decimal

    def technique(self, side: AthleteSide) -> Decimal:
        return self.technique_red if side == AthleteSide.RED else self.technique_blue

    def presentation(self, side: AthleteSide) -> Decimal:
        return self.presentation_red if side == AthleteSide.RED else self.presentation_blue

    def total(self, side: AthleteSide) -> Decimal:
        return self.technique(side) + self.presentation(side)


@dataclass(frozen=True)
class JudgeScorecard:
    session_id: str
    judge_name: str
    rounds: tuple[RoundScore, ...]
    total_events: int
    last_sequence: int

    def round(self, round_number: int) -> RoundScore | None:
        return next((item for item in self.rounds if item.round_number == round_number), None)

    def final_score(self, side: AthleteSide) -> Decimal:
        if not self.rounds:
            return round2(_ZERO)
        count = Decimal(len(self.rounds))
        technique = round2(sum((item.technique(side) for item in self.rounds), _ZERO) / count)
        presentation = round2(sum((item.presentation(side) for item in self.rounds), _ZERO) / count)
        return round2(technique + presentation)

    @property
    def final_score_red(self) -> Decimal:
        return self.final_score(AthleteSide.RED)

    @property
    def final_score_blue(self) -> Decimal:
        return self.final_score(AthleteSide.BLUE)


def build_judge_scorecard(
    *,
    session_id: str,
    judge_name: str,
    events: Iterable[ScoreEvent],
    round_numbers: Iterable[int],
    technique_start: Decimal,
    presentation_category_start: Decimal,
    session_ids: Sequence[str] | None = None,
) -> JudgeScorecard:
    """Scorecard of one judge over the given rounds; events of other judges are ignored.

    session_ids: the sessions of the judge in connection order when it replaced its session (defaults to
    session_id alone); their events form one scorecard.
    """
    rank = {item: index for index, item in enumerate(session_ids or (session_id,))}

    def order(event: ScoreEvent) -> tuple[int, int]:
        return rank[event.session_id], event.sequence

    judge_events = sorted((event for event in events if event.session_id in rank), key=order)
    technique_bounds = target_bounds(
        ScoreTarget.TECHNIQUE,
        technique_start=technique_start,
        presentation_category_start=presentation_category_start,
    )
    category_bounds = target_bounds(
        ScoreTarget.PRESENTATION_SPEED_POWER,
        technique_start=technique_start,
        presentation_category_start=presentation_category_start,
    )

    def technique(side: AthleteSide, round_number: int) -> Decimal:
        return running_target_score(
            events=judge_events,
            side=side,
            round_number=round_number,
            target=ScoreTarget.TECHNIQUE,
            bounds=technique_bounds,
            sort_key=order,
        )

    def presentation(side: AthleteSide, round_number: int) -> Decimal:
        return sum(
            (
                running_target_score(
                    events=judge_events,
                    side=side,
                    round_number=round_number,
                    target=target,
                    bounds=category_bounds,
                    sort_key=order,
                )
                for target in PRESENTATION_TARGETS
            ),
            _ZERO,
        ).quantize(_SCORE_STEP)

    rounds = tuple(
        RoundScore(
            round_number=round_number,
            technique_red=technique(AthleteSide.RED, round_number),
            presentation_red=presentation(AthleteSide.RED, round_number),
            technique_blue=technique(AthleteSide.BLUE, round_number),
            presentation_blue=presentation(AthleteSide.BLUE, round_number),
        )
        for round_number in sorted({int(item) for item in round_numbers if int(item) > 0})
    )
    return JudgeScorecard(
        session_id=session_id,
        judge_name=judge_name,
        rounds=rounds,
        total_events=len(judge_events),
        # Sequence of the judge's latest event (the latest session's own numbering after a replacement).
        last_sequence=judge_events[-1].sequence if judge_events else 0,
    )


def judge_aliases(session_ids: Iterable[str]) -> dict[str, str]:
    """J1..Jn in the given order (the order in which the judges first connected to the station)."""
    aliases: dict[str, str] = {}
    for session_id in session_ids:
        if session_id not in aliases:
            aliases[session_id] = f"J{len(aliases) + 1}"
    return aliases


def _clamp(value: Decimal, maximum: Decimal) -> Decimal:
    return min(maximum, max(_ZERO, value))
