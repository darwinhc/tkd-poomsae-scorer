from tkd_scorer.application.dto.station_dto import StationView
from tkd_scorer.domain.entities.station import Station


def to_station_view(station: Station) -> StationView:
    return StationView(
        id=station.id,
        name=station.name,
        status=station.status.value,
        expected_judge_name=station.expected_judge_name,
        active_session_id=station.active_session_id,
    )
