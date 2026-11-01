from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tkd_scorer.domain.entities.common import StationStatus


@dataclass
class Station:
    id: str
    name: str
    status: StationStatus
    credential_hash: str
    # The PIN encrypted with the server key (see CredentialCipherPort) so the admin panel can show it;
    # connections are verified against credential_hash only.
    credential_encrypted: str | None = None
    credential_expires_at: datetime | None = None
    expected_judge_name: str | None = None
    active_session_id: str | None = None
    updated_at: datetime | None = None

    def mark_connected(self, session_id: str) -> None:
        self.active_session_id = session_id
        self.status = StationStatus.OCCUPIED

    def mark_disconnected(self) -> None:
        self.active_session_id = None
        self.status = StationStatus.ACTIVE
