from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReminderRequest:
    """One accepted reminder: what to say, when it was asked, when it is due."""

    request_id: str
    dedupe_key: str
    title: str
    text: str
    delay_seconds: int
    requested_at: datetime
    notify_at: datetime
