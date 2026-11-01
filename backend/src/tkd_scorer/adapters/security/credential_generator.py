import secrets

from tkd_scorer.ports.services.credential_generator_port import CredentialGeneratorPort


class NumericCredentialGenerator(CredentialGeneratorPort):
    def generate(self, *, length: int = 6) -> str:
        max_value = 10**length
        value = secrets.randbelow(max_value)
        return str(value).zfill(length)
