from tkd_scorer.infra.websocket.connection_hub import ConnectionHub
from tkd_scorer.ports.realtime.realtime_port import RealtimePort


class FastApiRealtimeAdapter(RealtimePort):
    def __init__(self, hub: ConnectionHub) -> None:
        self._hub = hub

    async def publish_to_session(self, session_id: str, event_type: str, payload: dict) -> None:
        await self._hub.send_to_session(
            session_id,
            {
                "type": event_type,
                "eventType": event_type,
                "payload": payload,
            },
        )

    async def publish_to_station(self, station_id: str, event_type: str, payload: dict) -> None:
        await self._hub.send_to_station(
            station_id,
            {
                "type": event_type,
                "eventType": event_type,
                "payload": payload,
            },
        )


class RealtimeRecorderAdapter(RealtimePort):
    """Simple adapter for tests."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish_to_session(self, session_id: str, event_type: str, payload: dict) -> None:
        self.events.append(
            {
                "target": "session",
                "session_id": session_id,
                "event_type": event_type,
                "payload": payload,
            }
        )

    async def publish_to_station(self, station_id: str, event_type: str, payload: dict) -> None:
        self.events.append(
            {
                "target": "station",
                "station_id": station_id,
                "event_type": event_type,
                "payload": payload,
            }
        )
