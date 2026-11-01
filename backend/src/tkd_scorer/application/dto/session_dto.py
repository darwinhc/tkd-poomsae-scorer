from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RestoreSessionInput:
    access_token: str
    # Accept a session that is no longer active (revoked after finalizing), e.g. to replay a finalization.
    allow_inactive: bool = False


@dataclass(frozen=True)
class RestoreSessionOutput:
    session_id: str
    station_id: str
    judge_name: str
    expires_at: datetime | None
    status: str


@dataclass(frozen=True)
class KickJudgeSessionOutput:
    station_id: str
    session_id: str
    judge_name: str
    status: str
    remaining_active_sessions: int
    message: str
