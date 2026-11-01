from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BootstrapPayload:
    base_url: str
    station_id: str | None
    station_name: str | None
    bootstrap_token: str
    environment: str
    tournament_id: str
    protocol_version: str
    expires_at: datetime


@dataclass(frozen=True)
class GenerateBootstrapInput:
    tournament_id: str
    station_id: str | None = None
    station_name: str | None = None


@dataclass(frozen=True)
class ValidateBootstrapInput:
    bootstrap_token: str
