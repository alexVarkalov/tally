from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tally.persistence import BotUser
from tally.repositories import UserRepository


def user_has_access(user: BotUser, admin_user_ids: frozenset[int]) -> bool:
    return user.is_allowed or user.telegram_id in admin_user_ids


def resolve_timezone(name: str | None) -> ZoneInfo:
    """IANA name → ZoneInfo, falling back to UTC for missing or unknown names."""
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        return ZoneInfo("UTC")


class UserService:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    async def record_seen(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
    ) -> BotUser:
        return await self._user_repo.record_seen(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )

    async def is_allowed(self, telegram_id: int) -> bool:
        user = await self._user_repo.get(telegram_id)
        return False if user is None else user.is_allowed

    async def get_user(self, telegram_id: int) -> BotUser | None:
        return await self._user_repo.get(telegram_id)

    async def set_allowed(self, telegram_id: int, allowed: bool) -> BotUser:
        return await self._user_repo.set_allowed(telegram_id, allowed)

    async def set_timezone(self, telegram_id: int, timezone: str) -> BotUser:
        normalized = timezone.strip()
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            msg = f"Unknown timezone: {timezone}"
            raise ValueError(msg) from exc
        return await self._user_repo.set_timezone(telegram_id, normalized)

    async def list_recent(self, limit: int = 50) -> list[BotUser]:
        return await self._user_repo.list_recent(limit)
