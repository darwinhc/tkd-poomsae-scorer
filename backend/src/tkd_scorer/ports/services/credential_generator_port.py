from abc import ABC, abstractmethod


class CredentialGeneratorPort(ABC):
    @abstractmethod
    def generate(self, *, length: int = 6) -> str:
        raise NotImplementedError
