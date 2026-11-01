from abc import ABC, abstractmethod
from decimal import Decimal

from tkd_scorer.domain.entities.common import AthleteSide
from tkd_scorer.domain.entities.score_event import ScoreEvent


class ScoreEventRepositoryPort(ABC):
    @abstractmethod
    def save(self, event: ScoreEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_for_match(self, match_id: str) -> list[ScoreEvent]:
        raise NotImplementedError

    @abstractmethod
    def list_for_match_round(self, match_id: str, round_number: int) -> list[ScoreEvent]:
        raise NotImplementedError

    @abstractmethod
    def delete_for_match_round(self, match_id: str, round_number: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_for_match(self, match_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_last_sequence(self, match_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_latest_score(self, match_id: str, side: AthleteSide, round_number: int, default: Decimal) -> Decimal:
        raise NotImplementedError
