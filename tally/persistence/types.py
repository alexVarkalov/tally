from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BotUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    preferred_locale: str | None
    timezone: str | None
    is_allowed: bool
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class Tracker:
    id: int
    key: str
    label: str
    worksheet: str
    position: int
    archived_at: datetime | None
    created_at: datetime

    @property
    def is_active(self) -> bool:
        return self.archived_at is None
