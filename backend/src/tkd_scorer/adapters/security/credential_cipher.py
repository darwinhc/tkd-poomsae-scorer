"""Fernet encryption of station credentials with a key derived from the server secret (TKD_JWT_SECRET_KEY).

Key derivation: HKDF-SHA256 over the UTF-8 secret, no salt, info "tkd-scorer/station-credential/v1",
32 bytes, URL-safe base64 encoded as the Fernet key. The info label keeps this key distinct from any other
use of the same secret (the JWT signature uses the secret directly). If the secret changes, stored values
can no longer be decrypted: decrypt() returns None and the operator rotates the credential.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from tkd_scorer.ports.security.credential_cipher_port import CredentialCipherPort

_HKDF_INFO = b"tkd-scorer/station-credential/v1"


def derive_credential_key(secret_key: str) -> bytes:
    raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(secret_key.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


class FernetCredentialCipher(CredentialCipherPort):
    def __init__(self, *, secret_key: str) -> None:
        self._fernet = Fernet(derive_credential_key(secret_key))

    def encrypt(self, plain_credential: str) -> str:
        return self._fernet.encrypt(plain_credential.encode("utf-8")).decode("ascii")

    def decrypt(self, encrypted_credential: str) -> str | None:
        try:
            return self._fernet.decrypt(encrypted_credential.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeError):
            return None
