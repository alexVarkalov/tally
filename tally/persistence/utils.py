from __future__ import annotations

from datetime import UTC, datetime

from tally.persistence.models import UserRecord
from tally.persistence.types import BotUser


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def to_user(record: UserRecord) -> BotUser:
    return BotUser(
        telegram_id=record.telegram_id,
        username=record.username,
        first_name=record.first_name,
        last_name=record.last_name,
        language_code=record.language_code,
        preferred_locale=record.preferred_locale,
        timezone=record.timezone,
        is_allowed=bool(record.is_allowed),
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_seen_at=record.last_seen_at,
    )
