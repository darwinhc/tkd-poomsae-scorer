from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StationView:
    id: str
    name: str
    status: str
    expected_judge_name: str | None
    active_session_id: str | None


@dataclass(frozen=True)
class ConnectStationInput:
    station_id: str
    judge_name: str
    credential: str
    device_id: str
    # Revoke this judge's active session on another device and take over its scorecard instead of a 409.
    replace_existing_judge_session: bool = False


@dataclass(frozen=True)
class ConnectStationOutput:
    session_id: str
    access_token: str
    expires_at: datetime | None
    station: StationView
