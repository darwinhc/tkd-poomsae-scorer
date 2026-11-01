from tkd_scorer.application.dto.station_dto import StationView
from tkd_scorer.application.mappers.station_mapper import to_station_view
from tkd_scorer.ports.repositories.station_repository_port import StationRepositoryPort


class ListActiveStationsUseCase:
    def __init__(self, *, station_repository: StationRepositoryPort) -> None:
        self._station_repository = station_repository

    def execute(self) -> list[StationView]:
        return [to_station_view(item) for item in self._station_repository.list_active()]
