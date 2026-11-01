from abc import ABC, abstractmethod


class ChecksumServicePort(ABC):
    @abstractmethod
    def compute(self, payload: dict) -> str:
        raise NotImplementedError

    @abstractmethod
    def verify(self, payload: dict, checksum: str) -> bool:
        raise NotImplementedError
