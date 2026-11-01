from abc import ABC, abstractmethod


class IdGeneratorPort(ABC):
    @abstractmethod
    def new(self, prefix: str | None = None) -> str:
        raise NotImplementedError
