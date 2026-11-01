from abc import ABC, abstractmethod


class StationCredentialServicePort(ABC):
    @abstractmethod
    def verify(self, plain_credential: str, credential_hash: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def hash_credential(self, plain_credential: str) -> str:
        raise NotImplementedError
