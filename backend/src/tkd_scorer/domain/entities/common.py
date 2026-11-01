from enum import StrEnum


class StationStatus(StrEnum):
    ACTIVE = "active"
    OCCUPIED = "occupied"
    OFFLINE = "offline"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    CLOSED = "closed"


class MatchStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    FINALIZATION_PENDING = "finalization_pending"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class RoundStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    FINISHED = "finished"


class AthleteSide(StrEnum):
    RED = "red"
    BLUE = "blue"


class ScoreTarget(StrEnum):
    TECHNIQUE = "TECHNIQUE"
    PRESENTATION_SPEED_POWER = "PRESENTATION_SPEED_POWER"
    PRESENTATION_RHYTHM_TEMPO = "PRESENTATION_RHYTHM_TEMPO"
    PRESENTATION_ENERGY_EXPRESSION = "PRESENTATION_ENERGY_EXPRESSION"
