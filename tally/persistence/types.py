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
