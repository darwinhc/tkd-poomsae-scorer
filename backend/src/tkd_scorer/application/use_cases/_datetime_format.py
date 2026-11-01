from __future__ import annotations

from datetime import UTC, datetime


def to_iso_utc_z(value: datetime) -> str:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=UTC)
    else:
        normalized = value.astimezone(UTC)
    return normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z")
