from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from tkd_scorer.domain.entities.common import AthleteSide
from tkd_scorer.domain.exceptions.errors import ValidationError
from tkd_scorer.domain.services.judge_scorecard import JudgeScorecard


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalize_rule_count(judges_required: int) -> int:
    if judges_required <= 4:
        return 3
    if judges_required <= 6:
        return 5
    return 7


def consolidated_score_for_judges(scores: list[Decimal], judges_required: int) -> Decimal:
    if judges_required <= 0:
        raise ValidationError("judges_required must be positive")
    if len(scores) < judges_required:
        raise ValidationError("not enough judge scores to consolidate")

    window = scores[:judges_required]
    rule_count = _normalize_rule_count(judges_required)
    if rule_count == 3:
        return _round2(sum(window) / Decimal(str(len(window))))

    if len(window) <= 2:
        return _round2(sum(window) / Decimal(str(len(window))))
    trimmed = sorted(window)[1:-1]
    if not trimmed:
        return _round2(sum(window) / Decimal(str(len(window))))
    divisor = Decimal(str(len(trimmed)))
    return _round2(sum(trimmed) / divisor)


REMATCH = "rematch"


def winner_side(red_score: Decimal, blue_score: Decimal) -> str:
    if red_score > blue_score:
        return "red"
    if blue_score > red_score:
        return "blue"
    return "draw"


def consolidate_scores(scores: list[Decimal]) -> Decimal:
    """Consolidates one part (technique or presentation) of one round across the judges that scored it.

    3 judges (or any count below 5): mean. 5, 6, 7 or more: drop one highest and one lowest, mean of the rest.
    Rounded to 2 decimals, half up.
    """
    if not scores:
        raise ValidationError("at least one judge score is required to consolidate")
    return consolidated_score_for_judges(list(scores), len(scores))


@dataclass(frozen=True)
class ConsolidatedRound:
    round_number: int
    judges_count: int
    technique_red: Decimal
    presentation_red: Decimal
    technique_blue: Decimal
    presentation_blue: Decimal
    # Sum of every judge's technique plus presentation in this round, including the scores dropped as
    # highest and lowest (tie-break).
    all_judges_red: Decimal = Decimal("0")
    all_judges_blue: Decimal = Decimal("0")

    def technique(self, side: AthleteSide) -> Decimal:
        return self.technique_red if side == AthleteSide.RED else self.technique_blue

    def presentation(self, side: AthleteSide) -> Decimal:
        return self.presentation_red if side == AthleteSide.RED else self.presentation_blue

    def all_judges(self, side: AthleteSide) -> Decimal:
        return self.all_judges_red if side == AthleteSide.RED else self.all_judges_blue

    def score(self, side: AthleteSide) -> Decimal:
        """Poomsae (round) score: consolidated technique plus consolidated presentation."""
        return _round2(self.technique(side) + self.presentation(side))

    @property
    def score_red(self) -> Decimal:
        return self.score(AthleteSide.RED)

    @property
    def score_blue(self) -> Decimal:
        return self.score(AthleteSide.BLUE)


@dataclass(frozen=True)
class ConsolidatedMatch:
    rounds: tuple[ConsolidatedRound, ...]
    judges_count: int

    def round(self, round_number: int) -> ConsolidatedRound | None:
        return next((item for item in self.rounds if item.round_number == round_number), None)

    def score(self, side: AthleteSide) -> Decimal | None:
        """Match score: mean of the round scores, 2 decimals half up."""
        if not self.rounds:
            return None
        total = sum((item.score(side) for item in self.rounds), Decimal("0"))
        return _round2(total / Decimal(len(self.rounds)))

    def presentation_total(self, side: AthleteSide) -> Decimal:
        return _round2(sum((item.presentation(side) for item in self.rounds), Decimal("0")))

    def all_judges_total(self, side: AthleteSide) -> Decimal:
        """Every judge's technique and presentation over all rounds, dropped scores included."""
        return _round2(sum((item.all_judges(side) for item in self.rounds), Decimal("0")))

    def technique_average(self, side: AthleteSide) -> Decimal | None:
        if not self.rounds:
            return None
        return _round2(sum((item.technique(side) for item in self.rounds), Decimal("0")) / Decimal(len(self.rounds)))

    def presentation_average(self, side: AthleteSide) -> Decimal | None:
        if not self.rounds:
            return None
        return _round2(self.presentation_total(side) / Decimal(len(self.rounds)))

    @property
    def score_red(self) -> Decimal | None:
        return self.score(AthleteSide.RED)

    @property
    def score_blue(self) -> Decimal | None:
        return self.score(AthleteSide.BLUE)

    @property
    def winner(self) -> str | None:
        if self.score_red is None or self.score_blue is None:
            return None
        return resolve_winner(
            score_red=self.score_red,
            score_blue=self.score_blue,
            presentation_red=self.presentation_total(AthleteSide.RED),
            presentation_blue=self.presentation_total(AthleteSide.BLUE),
            all_judges_red=self.all_judges_total(AthleteSide.RED),
            all_judges_blue=self.all_judges_total(AthleteSide.BLUE),
        )


def consolidate_scorecards(scorecards: list[JudgeScorecard]) -> ConsolidatedMatch:
    """Consolidates per round, per side, technique and presentation separately.

    Each round uses the judges whose scorecard contains that round.
    """
    round_numbers = sorted({item.round_number for card in scorecards for item in card.rounds})
    rounds: list[ConsolidatedRound] = []
    for round_number in round_numbers:
        samples = [round_score for card in scorecards if (round_score := card.round(round_number)) is not None]
        rounds.append(
            ConsolidatedRound(
                round_number=round_number,
                judges_count=len(samples),
                technique_red=consolidate_scores([item.technique_red for item in samples]),
                presentation_red=consolidate_scores([item.presentation_red for item in samples]),
                technique_blue=consolidate_scores([item.technique_blue for item in samples]),
                presentation_blue=consolidate_scores([item.presentation_blue for item in samples]),
                all_judges_red=sum((item.total(AthleteSide.RED) for item in samples), Decimal("0")),
                all_judges_blue=sum((item.total(AthleteSide.BLUE) for item in samples), Decimal("0")),
            )
        )
    return ConsolidatedMatch(rounds=tuple(rounds), judges_count=len(scorecards))


def resolve_winner(
    *,
    score_red: Decimal,
    score_blue: Decimal,
    presentation_red: Decimal,
    presentation_blue: Decimal,
    all_judges_red: Decimal | None = None,
    all_judges_blue: Decimal | None = None,
) -> str:
    """Tie-break: the higher match score wins; if equal, the higher consolidated presentation (summed over
    the rounds); if still equal, the higher sum of all judges' scores (technique and presentation of every
    round, including the highest and lowest dropped by the consolidation).

    If every step is equal the result is REMATCH ("rematch"): the competitors perform again.
    """
    steps = [(score_red, score_blue), (presentation_red, presentation_blue)]
    if all_judges_red is not None and all_judges_blue is not None:
        steps.append((all_judges_red, all_judges_blue))
    for red, blue in steps:
        result = winner_side(red, blue)
        if result != "draw":
            return result
    return REMATCH
