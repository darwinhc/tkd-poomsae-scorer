from abc import ABC, abstractmethod


class CredentialCipherPort(ABC):
    """Reversible encryption of a station credential, so the admin panel can show it again."""

    @abstractmethod
    def encrypt(self, plain_credential: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def decrypt(self, encrypted_credential: str) -> str | None:
        """The plain credential, or None when it cannot be decrypted (e.g. the server key changed)."""
        raise NotImplementedError
