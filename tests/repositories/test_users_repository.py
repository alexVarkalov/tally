from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tally.repositories.users import UserRepository


@pytest.mark.asyncio
async def test_user_repository_record_seen_forwards_fields() -> None:
    db = AsyncMock()
    repo = UserRepository(db)

    await repo.record_seen(telegram_id=1, username="tester", first_name="Test", last_name="User", language_code="en")

    db.upsert_user_seen.assert_awaited_once_with(
        telegram_id=1, username="tester", first_name="Test", last_name="User", language_code="en"
    )


@pytest.mark.asyncio
async def test_user_repository_methods_delegate_to_db() -> None:
    db = AsyncMock()
    repo = UserRepository(db)

    await repo.get(1)
    await repo.set_allowed(1, True)
    await repo.set_timezone(1, "UTC")
    await repo.list_recent(limit=3)

    db.get_user.assert_awaited_once_with(1)
    db.set_user_allowed.assert_awaited_once_with(1, True)
    db.set_user_timezone.assert_awaited_once_with(1, "UTC")
    db.list_users.assert_awaited_once_with(3)
