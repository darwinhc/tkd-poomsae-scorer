from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal


def to_json_payload(value: object) -> str:
    def _default_encoder(item: object) -> object:
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, datetime):
            return item.isoformat()
        if is_dataclass(item):
            return asdict(item)
        raise TypeError(f"Type {type(item)!r} is not JSON serializable")

    return json.dumps(value, default=_default_encoder, sort_keys=True)


def from_json_payload(payload: str) -> dict:
    return json.loads(payload)
