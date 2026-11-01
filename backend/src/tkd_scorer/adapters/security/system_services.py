from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from tkd_scorer.domain.exceptions.errors import UnauthorizedError
from tkd_scorer.ports.security.station_credential_service_port import StationCredentialServicePort
from tkd_scorer.ports.security.token_service_port import TokenServicePort


class JwtTokenService(TokenServicePort):
    def __init__(self, *, secret_key: str, algorithm: str, token_ttl_seconds: int) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._token_ttl_seconds = token_ttl_seconds

    def issue_access_token(self, *, session_id: str, station_id: str, judge_name: str) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self._token_ttl_seconds)
        claims = {
            "session_id": session_id,
            "station_id": station_id,
            "judge_name": judge_name,
            "exp": int(expires_at.timestamp()),
            "typ": "access",
        }
        return jwt.encode(claims, self._secret_key, algorithm=self._algorithm)

    def parse_access_token(self, token: str) -> dict[str, str]:
        try:
            claims = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        except JWTError as exc:
            raise UnauthorizedError("Invalid access token") from exc
        return {key: str(value) for key, value in claims.items() if key != "exp"}

    def hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PasswordStationCredentialService(StationCredentialServicePort):
    def __init__(self) -> None:
        self._context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

    def verify(self, plain_credential: str, credential_hash: str) -> bool:
        return self._context.verify(plain_credential, credential_hash)

    def hash_credential(self, plain_credential: str) -> str:
        return self._context.hash(plain_credential)
