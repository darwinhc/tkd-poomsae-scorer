import uuid
from datetime import datetime, timezone

from tkd_scorer.ports.clock.clock_port import ClockPort
from tkd_scorer.ports.id_generator.id_generator_port import IdGeneratorPort


class UtcClock(ClockPort):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class UuidIdGenerator(IdGeneratorPort):
    def new(self, prefix: str | None = None) -> str:
        value = str(uuid.uuid4())
        if prefix:
            return f"{prefix}-{value}"
        return value
