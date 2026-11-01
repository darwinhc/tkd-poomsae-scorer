from tkd_scorer.application.dto.bootstrap_dto import ValidateBootstrapInput
from tkd_scorer.domain.exceptions.errors import UnauthorizedError
from tkd_scorer.ports.services.bootstrap_service_port import BootstrapServicePort


class ValidateBootstrapUseCase:
    def __init__(self, *, bootstrap_service: BootstrapServicePort) -> None:
        self._bootstrap_service = bootstrap_service

    def execute(self, request: ValidateBootstrapInput) -> dict[str, str]:
        claims = self._bootstrap_service.validate_bootstrap_token(request.bootstrap_token)
        if not claims:
            raise UnauthorizedError("Invalid bootstrap token")
        return claims
