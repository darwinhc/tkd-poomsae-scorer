from __future__ import annotations

from datetime import datetime

from jose import JWTError, jwt

from tkd_scorer.domain.exceptions.errors import UnauthorizedError
from tkd_scorer.ports.services.bootstrap_service_port import BootstrapServicePort


class JwtBootstrapService(BootstrapServicePort):
    def __init__(self, *, secret_key: str, algorithm: str) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm

    def issue_bootstrap_token(self, *, tournament_id: str, expires_at: datetime) -> str:
        claims = {
            "tournament_id": tournament_id,
            "exp": int(expires_at.timestamp()),
            "typ": "bootstrap",
        }
        return jwt.encode(claims, self._secret_key, algorithm=self._algorithm)

    def validate_bootstrap_token(self, token: str) -> dict[str, str]:
        try:
            claims = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        except JWTError as exc:
            raise UnauthorizedError("Invalid bootstrap token") from exc
        return {key: str(value) for key, value in claims.items() if key != "exp"}
