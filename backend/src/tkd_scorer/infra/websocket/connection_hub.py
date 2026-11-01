from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass
class ConnectionBinding:
    connection_id: str
    websocket: WebSocket
    session_id: str | None = None
    station_id: str | None = None
    device_id: str | None = None


class ConnectionHub:
    def __init__(self) -> None:
        self._connections: dict[str, ConnectionBinding] = {}
        self._by_session: dict[str, set[str]] = defaultdict(set)
        self._by_station: dict[str, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()

    async def register(self, connection_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            with self._sync_lock:
                self._connections[connection_id] = ConnectionBinding(
                    connection_id=connection_id,
                    websocket=websocket,
                )

    async def bind(
        self,
        connection_id: str,
        *,
        session_id: str,
        station_id: str,
        device_id: str | None,
    ) -> None:
        async with self._lock:
            with self._sync_lock:
                binding = self._connections[connection_id]
                if binding.session_id:
                    self._by_session[binding.session_id].discard(connection_id)
                if binding.station_id:
                    self._by_station[binding.station_id].discard(connection_id)

                binding.session_id = session_id
                binding.station_id = station_id
                binding.device_id = device_id
                self._by_session[session_id].add(connection_id)
                self._by_station[station_id].add(connection_id)

    async def unregister(self, connection_id: str) -> ConnectionBinding | None:
        async with self._lock:
            with self._sync_lock:
                binding = self._connections.pop(connection_id, None)
                if binding is None:
                    return None
                if binding.session_id:
                    self._by_session[binding.session_id].discard(connection_id)
                if binding.station_id:
                    self._by_station[binding.station_id].discard(connection_id)
                return binding

    async def send_to_session(self, session_id: str, event: dict) -> None:
        with self._sync_lock:
            targets = self._by_session.get(session_id, set()).copy()
        await self._send_to_targets(targets, event)

    async def send_to_station(self, station_id: str, event: dict) -> None:
        with self._sync_lock:
            targets = self._by_station.get(station_id, set()).copy()
        await self._send_to_targets(targets, event)

    def binding_for(self, connection_id: str) -> ConnectionBinding | None:
        with self._sync_lock:
            return self._connections.get(connection_id)

    def is_session_connected(self, session_id: str) -> bool:
        with self._sync_lock:
            connection_ids = self._by_session.get(session_id, set())
            return any(connection_id in self._connections for connection_id in connection_ids)

    def connected_session_ids_for_station(self, station_id: str) -> set[str]:
        with self._sync_lock:
            connection_ids = self._by_station.get(station_id, set()).copy()
            connected_session_ids: set[str] = set()
            for connection_id in connection_ids:
                binding = self._connections.get(connection_id)
                if binding is None or not binding.session_id:
                    continue
                connected_session_ids.add(binding.session_id)
            return connected_session_ids

    async def _send_to_targets(self, connection_ids: set[str], event: dict) -> None:
        stale: list[str] = []
        for connection_id in connection_ids:
            with self._sync_lock:
                binding = self._connections.get(connection_id)
                websocket = binding.websocket if binding else None
            if websocket is None:
                continue
            try:
                await websocket.send_json(event)
            except Exception:
                stale.append(connection_id)
        for connection_id in stale:
            await self.unregister(connection_id)
