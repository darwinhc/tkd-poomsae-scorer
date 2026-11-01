from abc import ABC, abstractmethod

from tkd_scorer.domain.entities.device_session import DeviceSession


class SessionRepositoryPort(ABC):
    @abstractmethod
    def save(self, session: DeviceSession) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, session_id: str) -> DeviceSession | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_token_hash(self, token_hash: str) -> DeviceSession | None:
        raise NotImplementedError

    @abstractmethod
    def revoke(self, session_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_active_by_station(self, station_id: str) -> DeviceSession | None:
        raise NotImplementedError

    @abstractmethod
    def list_active_by_station(self, station_id: str) -> list[DeviceSession]:
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> list[DeviceSession]:
        raise NotImplementedError
