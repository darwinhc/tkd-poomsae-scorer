from abc import ABC, abstractmethod


class TokenServicePort(ABC):
    @abstractmethod
    def issue_access_token(self, *, session_id: str, station_id: str, judge_name: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def parse_access_token(self, token: str) -> dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def hash_token(self, token: str) -> str:
        raise NotImplementedError
