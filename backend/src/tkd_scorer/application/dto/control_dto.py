from dataclasses import dataclass


@dataclass(frozen=True)
class CommandAck:
    match_id: str
    message: str
