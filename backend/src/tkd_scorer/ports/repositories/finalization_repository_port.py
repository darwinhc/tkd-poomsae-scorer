from abc import ABC, abstractmethod

from tkd_scorer.domain.entities.score_event import FinalizationRecord


class FinalizationRepositoryPort(ABC):
    @abstractmethod
    def get_by_idempotency_key(self, idempotency_key: str) -> FinalizationRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, record: FinalizationRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_for_match(self, match_id: str) -> list[FinalizationRecord]:
        """Finalizations of a match, oldest first (one per judge in normal operation)."""
        raise NotImplementedError

    @abstractmethod
    def delete_for_match(self, match_id: str) -> None:
        """Removes every judge finalization of a match (the match was reset)."""
        raise NotImplementedError
