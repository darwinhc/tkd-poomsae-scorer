from abc import ABC, abstractmethod

from tkd_scorer.domain.entities.score_event import IdempotencyRecord


class IdempotencyRepositoryPort(ABC):
    @abstractmethod
    def get(self, key: str) -> IdempotencyRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, record: IdempotencyRecord) -> None:
        raise NotImplementedError
