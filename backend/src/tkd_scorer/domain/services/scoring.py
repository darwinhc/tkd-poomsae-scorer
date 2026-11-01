from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from tkd_scorer.domain.entities.score_event import ScoreEvent


def compute_score(starting_score: Decimal, events: Iterable[ScoreEvent]) -> Decimal:
    total = starting_score
    for event in sorted(events, key=lambda item: item.sequence):
        total += event.score_delta
    return total.quantize(Decimal("0.1"))
