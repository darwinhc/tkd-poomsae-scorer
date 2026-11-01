import pytest

from tkd_scorer.infra.websocket.connection_hub import ConnectionHub


class DummyWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_connection_hub_dispatches_to_bound_station_and_session() -> None:
    hub = ConnectionHub()
    ws = DummyWebSocket()

    await hub.register("conn-1", ws)
    await hub.bind("conn-1", session_id="sess-1", station_id="station-01", device_id="dev-1")

    await hub.send_to_station("station-01", {"eventType": "match_updated"})
    await hub.send_to_session("sess-1", {"eventType": "session_revoked"})

    assert ws.messages[0]["eventType"] == "match_updated"
    assert ws.messages[1]["eventType"] == "session_revoked"
