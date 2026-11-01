from abc import ABC, abstractmethod
from datetime import datetime


class BootstrapServicePort(ABC):
    @abstractmethod
    def issue_bootstrap_token(self, *, tournament_id: str, expires_at: datetime) -> str:
        raise NotImplementedError

    @abstractmethod
    def validate_bootstrap_token(self, token: str) -> dict[str, str]:
        raise NotImplementedError
