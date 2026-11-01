from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tkd_scorer.domain.entities.common import SessionStatus


@dataclass
class DeviceSession:
    id: str
    station_id: str
    judge_name: str
    device_id: str
    token_hash: str
    status: SessionStatus
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None = None
    # Set when this session replaced another session of the same judge (new device, or the same device
    # reconnecting): it continues that judge's scorecard instead of starting a new one.
    scorecard_session_id: str | None = None

    def revoke(self, at: datetime) -> None:
        self.status = SessionStatus.REVOKED
        self.revoked_at = at

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE

    @property
    def scorecard_key(self) -> str:
        """Identity of the judge scorecard this session writes to (its own ID unless it replaced a session)."""
        return self.scorecard_session_id or self.id
