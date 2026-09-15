from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tally.services.users import UserService, resolve_timezone, user_has_access
from tests.helpers import make_user


def test_user_has_access_allowed_user() -> None:
    assert user_has_access(make_user(is_allowed=True), frozenset()) is True


def test_user_has_access_blocked_user() -> None:
    assert user_has_access(make_user(is_allowed=False), frozenset()) is False


def test_user_has_access_admin_bypasses_block() -> None:
    assert user_has_access(make_user(telegram_id=7, is_allowed=False), frozenset({7})) is True


def test_resolve_timezone_falls_back_to_utc() -> None:
    assert resolve_timezone(None).key == "UTC"
    assert resolve_timezone("Not/AZone").key == "UTC"
    assert resolve_timezone("Europe/Warsaw").key == "Europe/Warsaw"


@pytest.mark.asyncio
async def test_record_seen_and_getters_delegate() -> None:
    repo = AsyncMock()
    repo.get.return_value = make_user(is_allowed=True)
    service = UserService(repo)

    await service.record_seen(telegram_id=1, username="u", first_name="f", last_name="l", language_code="en")
    assert await service.is_allowed(1) is True
    assert await service.get_user(1) is not None
    await service.set_allowed(1, False)
    await service.list_recent(limit=5)

    repo.record_seen.assert_awaited_once()
    repo.set_allowed.assert_awaited_once_with(1, False)
    repo.list_recent.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_is_allowed_false_for_unknown_user() -> None:
    repo = AsyncMock()
    repo.get.return_value = None

    assert await UserService(repo).is_allowed(1) is False


@pytest.mark.asyncio
async def test_set_timezone_validates_and_calls_repo() -> None:
    repo = AsyncMock()
    repo.set_timezone.return_value = make_user(timezone="Europe/Warsaw")
    service = UserService(repo)

    result = await service.set_timezone(1, " Europe/Warsaw ")

    assert result.timezone == "Europe/Warsaw"
    repo.set_timezone.assert_awaited_once_with(1, "Europe/Warsaw")


@pytest.mark.asyncio
async def test_set_timezone_rejects_invalid_timezone() -> None:
    service = UserService(AsyncMock())

    with pytest.raises(ValueError, match="Unknown timezone"):
        await service.set_timezone(1, "Mars/Colony")
