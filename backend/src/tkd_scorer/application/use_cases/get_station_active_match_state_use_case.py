from dataclasses import dataclass
from datetime import datetime

from tkd_scorer.domain.entities.common import MatchStatus
from tkd_scorer.domain.exceptions.errors import NotFoundError
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.repositories.match_repository_port import MatchRepositoryPort
from tkd_scorer.ports.repositories.session_repository_port import SessionRepositoryPort
from tkd_scorer.ports.repositories.station_repository_port import StationRepositoryPort


@dataclass(frozen=True)
class StationActiveMatchStateView:
    station_id: str
    has_active_match: bool
    match_id: str | None
    competitor_red_name: str | None
    competitor_blue_name: str | None
    updated_at: datetime


class GetStationActiveMatchStateUseCase:
    def __init__(
        self,
        *,
        station_repository: StationRepositoryPort,
        session_repository: SessionRepositoryPort,
        match_repository: MatchRepositoryPort,
        clock: ClockPort,
        lookup_limit: int = 50,
    ) -> None:
        self._station_repository = station_repository
        self._session_repository = session_repository
        self._match_repository = match_repository
        self._clock = clock
        self._lookup_limit = max(1, int(lookup_limit))

    def execute(self, station_id: str) -> StationActiveMatchStateView:
        station = self._station_repository.get_by_id(station_id)
        if station is None:
            raise NotFoundError("Station not found")

        candidates = self._match_repository.list_recent(
            limit=self._lookup_limit,
            statuses=[MatchStatus.IN_PROGRESS.value, MatchStatus.FINALIZATION_PENDING.value],
        )

        active_sessions = self._session_repository.list_active_by_station(station_id)
        for match in candidates:
            if match.station_id != station_id or not match.is_live(active_sessions):
                continue
            return StationActiveMatchStateView(
                station_id=station_id,
                has_active_match=True,
                match_id=match.id,
                competitor_red_name=match.competitor_left_name,
                competitor_blue_name=match.competitor_right_name,
                updated_at=self._clock.now(),
            )

        return StationActiveMatchStateView(
            station_id=station_id,
            has_active_match=False,
            match_id=None,
            competitor_red_name=None,
            competitor_blue_name=None,
            updated_at=self._clock.now(),
        )
