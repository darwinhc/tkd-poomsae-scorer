from abc import ABC, abstractmethod

from tkd_scorer.domain.entities.audit import AuditEvent


class AuditRepositoryPort(ABC):
    @abstractmethod
    def save(self, event: AuditEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_recent(
        self,
        *,
        limit: int,
        category: str | None = None,
        action: str | None = None,
        subject_id: str | None = None,
    ) -> list[AuditEvent]:
        raise NotImplementedError
