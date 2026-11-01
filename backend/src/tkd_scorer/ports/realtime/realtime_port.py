from abc import ABC, abstractmethod


class RealtimePort(ABC):
    @abstractmethod
    async def publish_to_session(self, session_id: str, event_type: str, payload: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    async def publish_to_station(self, station_id: str, event_type: str, payload: dict) -> None:
        raise NotImplementedError
