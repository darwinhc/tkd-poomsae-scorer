from datetime import timedelta

from tkd_scorer.application.dto.bootstrap_dto import BootstrapPayload, GenerateBootstrapInput
from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.services.bootstrap_service_port import BootstrapServicePort


class GenerateBootstrapUseCase:
    def __init__(
        self,
        *,
        bootstrap_service: BootstrapServicePort,
        clock: ClockPort,
        base_url: str,
        environment: str,
        protocol_version: str,
        bootstrap_ttl_seconds: int,
    ) -> None:
        self._bootstrap_service = bootstrap_service
        self._clock = clock
        self._base_url = base_url
        self._environment = environment
        self._protocol_version = protocol_version
        self._bootstrap_ttl_seconds = bootstrap_ttl_seconds

    def execute(self, request: GenerateBootstrapInput) -> BootstrapPayload:
        expires_at = self._clock.now() + timedelta(seconds=self._bootstrap_ttl_seconds)
        token = self._bootstrap_service.issue_bootstrap_token(
            tournament_id=request.tournament_id,
            expires_at=expires_at,
        )
        return BootstrapPayload(
            base_url=self._base_url,
            station_id=request.station_id,
            station_name=request.station_name,
            bootstrap_token=token,
            environment=self._environment,
            tournament_id=request.tournament_id,
            protocol_version=self._protocol_version,
            expires_at=expires_at,
        )
