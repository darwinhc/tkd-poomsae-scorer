from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class JudgeRoundCompletedSignalInput:
    match_id: str
    round_number: int
    session_id: str
    station_id: str
    judge_name: str
    device_id: str | None
    finished_at: datetime | None


@dataclass(frozen=True)
class JudgeMatchCompletedSignalInput:
    match_id: str
    final_round: int
    checksum: str
    session_id: str
    station_id: str
    judge_name: str
    device_id: str | None
    finished_at: datetime | None


@dataclass(frozen=True)
class JudgeSignalOutput:
    signal_type: str
    match_id: str
    station_id: str
    session_id: str
    judge_name: str
    accepted_at: datetime
