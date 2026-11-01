from __future__ import annotations

import hashlib

from tkd_scorer.domain.services.finalization_checksum import canonical_json
from tkd_scorer.ports.services.checksum_service_port import ChecksumServicePort


class Sha256ChecksumService(ChecksumServicePort):
    def compute(self, payload: dict) -> str:
        canonical = canonical_json(payload)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify(self, payload: dict, checksum: str) -> bool:
        return self.compute(payload) == checksum
