from __future__ import annotations

from tally.db import Database
from tally.persistence import BotUser


class UserRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def record_seen(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
    ) -> BotUser:
        return await self._db.upsert_user_seen(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )

    async def get(self, telegram_id: int) -> BotUser | None:
        return await self._db.get_user(telegram_id)

    async def set_allowed(self, telegram_id: int, allowed: bool) -> BotUser:
        return await self._db.set_user_allowed(telegram_id, allowed)

    async def set_timezone(self, telegram_id: int, timezone: str) -> BotUser:
        return await self._db.set_user_timezone(telegram_id, timezone)

    async def set_locale(self, telegram_id: int, locale: str) -> BotUser:
        return await self._db.set_user_locale(telegram_id, locale)

    async def list_recent(self, limit: int = 50) -> list[BotUser]:
        return await self._db.list_users(limit)
