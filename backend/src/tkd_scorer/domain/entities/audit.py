from dataclasses import dataclass
from datetime import datetime


@dataclass
class AuditEvent:
    id: str
    category: str
    action: str
    subject_id: str
    actor: str
    details: str
    occurred_at: datetime
