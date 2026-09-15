from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tally.handlers.common import (
    format_user_datetime,
    format_user_display,
    format_user_timezone,
    parse_target_user_id,
    record_user_seen,
    require_access,
    require_admin,
    user_has_access,
    user_timezone,
)
from tests.helpers import make_settings, make_user


def test_user_timezone_falls_back_to_default_then_utc() -> None:
    assert user_timezone(make_user(timezone=None), make_settings()).key == "Europe/Warsaw"
    assert user_timezone(make_user(timezone=None), make_settings(default_timezone="Bad/Zone")).key == "UTC"
    assert user_timezone(make_user(timezone="Not/AZone"), make_settings()).key == "UTC"
    assert user_timezone(make_user(timezone="Europe/Moscow"), make_settings()).key == "Europe/Moscow"


def test_format_user_datetime_uses_user_timezone() -> None:
    when = datetime(2026, 5, 6, 8, 0, tzinfo=UTC)
    assert format_user_datetime(when, make_user(timezone="Europe/Warsaw"), make_settings()) == (
        "2026-05-06 10:00 Europe/Warsaw"
    )


def test_format_user_timezone() -> None:
    assert format_user_timezone(make_user(timezone=None), make_settings()) == "Europe/Warsaw"
    assert format_user_timezone(make_user(timezone="UTC"), make_settings()) == "UTC"


def test_parse_target_user_id() -> None:
    assert parse_target_user_id(None) is None
    assert parse_target_user_id([]) is None
    assert parse_target_user_id(["abc"]) is None
    assert parse_target_user_id(("42",)) == 42


def test_format_user_display() -> None:
    assert format_user_display(make_user(username="tester")) == "@tester"
    assert format_user_display(make_user(username="", first_name="A", last_name="B")) == "A B"
    assert format_user_display(make_user(username="", first_name="", last_name="")) == "no profile name"


def test_user_has_access_uses_settings_admins() -> None:
    assert user_has_access(make_user(telegram_id=999, is_allowed=False), make_settings()) is True
    assert user_has_access(make_user(telegram_id=1, is_allowed=False), make_settings()) is False


def _context(user_service: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(
        application=SimpleNamespace(bot_data={"user_service": user_service, "settings": make_settings()})
    )


def _update(user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, username=None, first_name=None, last_name=None, language_code=None),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_record_user_seen_forwards_profile() -> None:
    user_service = AsyncMock()
    user_service.record_seen.return_value = make_user()
    context = _context(user_service)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=5, username="u", first_name="f", last_name="l", language_code="ru")
    )

    assert await record_user_seen(update, context) is not None
    assert await record_user_seen(SimpleNamespace(effective_user=None), context) is None

    user_service.record_seen.assert_awaited_once_with(
        telegram_id=5, username="u", first_name="f", last_name="l", language_code="ru"
    )


@pytest.mark.asyncio
async def test_require_access() -> None:
    user_service = AsyncMock()
    user_service.record_seen.side_effect = lambda **kw: make_user(telegram_id=kw["telegram_id"], is_allowed=False)
    context = _context(user_service)

    assert await require_access(update(999), context) is not None

    denied = update(1)
    assert await require_access(denied, context) is None
    denied.effective_message.reply_text.assert_awaited_once_with("This is a private bot.")

    assert await require_access(SimpleNamespace(effective_user=None, effective_message=None), context) is None


@pytest.mark.asyncio
async def test_require_access_allowed_user() -> None:
    user_service = AsyncMock()
    user_service.record_seen.return_value = make_user(telegram_id=1, is_allowed=True)

    user = await require_access(update(1), _context(user_service))

    assert user is not None and user.telegram_id == 1


@pytest.mark.asyncio
async def test_require_admin() -> None:
    user_service = AsyncMock()
    user_service.record_seen.return_value = make_user(telegram_id=1)
    context = _context(user_service)

    assert await require_admin(update(999), context) is True

    denied = update(1)
    assert await require_admin(denied, context) is False
    denied.effective_message.reply_text.assert_awaited_once()

    assert await require_admin(SimpleNamespace(effective_user=None, effective_message=None), context) is False


update = _update
