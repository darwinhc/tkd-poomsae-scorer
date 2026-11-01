from abc import ABC, abstractmethod

from tkd_scorer.domain.entities.station import Station


class StationRepositoryPort(ABC):
    @abstractmethod
    def list_all(self) -> list[Station]:
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> list[Station]:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, station_id: str) -> Station | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, station: Station) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, station_id: str) -> bool:
        raise NotImplementedError
