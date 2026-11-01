from abc import ABC, abstractmethod

from tkd_scorer.domain.entities.match import Match, MatchRound


class MatchRepositoryPort(ABC):
    @abstractmethod
    def save_match(self, match: Match) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_match(self, match_id: str) -> Match | None:
        raise NotImplementedError

    @abstractmethod
    def upsert_round(self, round_entity: MatchRound) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_round(self, match_id: str, round_number: int) -> MatchRound | None:
        raise NotImplementedError

    @abstractmethod
    def list_recent(self, *, limit: int, statuses: list[str] | None = None) -> list[Match]:
        raise NotImplementedError

    @abstractmethod
    def delete_match(self, match_id: str) -> bool:
        raise NotImplementedError
