from dataclasses import dataclass
from datetime import datetime

from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort


@dataclass(frozen=True)
class StationActiveSessionView:
    station_id: str
    session_id: str | None
    judge_name: str | None
    device_id: str | None
    expires_at: datetime | None
    active_sessions_count: int


class GetStationActiveSessionUseCase:
    def __init__(self, *, session_repository: SessionRepositoryPort) -> None:
        self._session_repository = session_repository

    def execute(self, station_id: str) -> StationActiveSessionView:
        sessions = self._session_repository.list_active_by_station(station_id)
        session = sessions[0] if sessions else None
        if session is None:
            return StationActiveSessionView(
                station_id=station_id,
                session_id=None,
                judge_name=None,
                device_id=None,
                expires_at=None,
                active_sessions_count=0,
            )
        return StationActiveSessionView(
            station_id=station_id,
            session_id=session.id,
            judge_name=session.judge_name,
            device_id=session.device_id,
            expires_at=session.expires_at,
            active_sessions_count=len(sessions),
        )
