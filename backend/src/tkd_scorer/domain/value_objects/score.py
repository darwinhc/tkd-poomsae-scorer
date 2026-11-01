from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from tkd_scorer.domain.exceptions.errors import ValidationError


@dataclass(frozen=True)
class ScoreDelta:
    value: Decimal

    def __post_init__(self) -> None:
        if self.value.is_nan() or self.value.is_infinite():
            raise ValidationError("scoreDelta must be a finite decimal")
        normalized = self.value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True)
class Score:
    value: Decimal

    def __post_init__(self) -> None:
        normalized = self.value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "value", normalized)

    def apply(self, delta: ScoreDelta) -> "Score":
        return Score(self.value + delta.value)
