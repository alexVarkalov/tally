from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tally.handlers import commands as commands_module
from tally.handlers import common as common_module
from tally.handlers.commands import cmd_help, cmd_menu, cmd_start, cmd_timezone, cmd_users
from tests.helpers import make_settings, make_tracker, make_user


def _ctx(args: list[str] | None = None) -> SimpleNamespace:
    tracker_service = AsyncMock()
    tracker_service.list_active.return_value = [make_tracker(key="my", label="MY")]
    return SimpleNamespace(
        args=list(args or []),
        application=SimpleNamespace(
            bot_data={"settings": make_settings(), "user_service": AsyncMock(), "tracker_service": tracker_service}
        ),
    )


def _update(with_user: bool = True, with_message: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=123) if with_user else None,
        effective_message=SimpleNamespace(reply_text=AsyncMock(), reply_html=AsyncMock()) if with_message else None,
    )


@pytest.mark.asyncio
async def test_cmd_start_no_message_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = AsyncMock(return_value=make_user())
    monkeypatch.setattr(common_module, "record_user_seen", seen)

    await cmd_start(_update(with_message=False), _ctx())

    seen.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_start_access_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=False)))

    await cmd_start(update, _ctx())

    update.effective_message.reply_text.assert_awaited_once_with("This is a private bot.")
    update.effective_message.reply_html.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_start_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=True)))

    await cmd_start(update, _ctx())

    update.effective_message.reply_html.assert_awaited_once()
    assert update.effective_message.reply_html.await_args.args[0] == "What do you want to record?"
    markup = update.effective_message.reply_html.await_args.kwargs["reply_markup"]
    assert [b.callback_data for row in markup.inline_keyboard for b in row][0] == "rec:my"


@pytest.mark.asyncio
async def test_cmd_start_with_empty_registry_points_at_new_and_attach(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    context = _ctx()
    context.application.bot_data["tracker_service"].list_active.return_value = []
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=True)))

    await cmd_start(update, context)

    text = update.effective_message.reply_html.await_args.args[0]
    assert "/new" in text and "/attach" in text


@pytest.mark.asyncio
async def test_cmd_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=True)))

    await cmd_menu(update, _ctx())

    update.effective_message.reply_html.assert_awaited_once()
    assert update.effective_message.reply_html.await_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_cmd_menu_access_disabled_or_no_message(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=False)))

    await cmd_menu(update, _ctx())
    await cmd_menu(_update(with_message=False), _ctx())

    update.effective_message.reply_html.assert_not_awaited()
    update.effective_message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_help_lists_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=True)))

    await cmd_help(update, _ctx())

    text = update.effective_message.reply_html.await_args.args[0]
    assert "/trackers" in text
    assert "/timezone" in text


@pytest.mark.asyncio
async def test_cmd_help_access_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=False)))

    await cmd_help(update, _ctx())
    await cmd_help(_update(with_message=False), _ctx())

    update.effective_message.reply_html.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_users_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(commands_module, "require_admin", AsyncMock(return_value=False))

    await cmd_users(update, _ctx())

    update.effective_message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_users_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    context = _ctx()
    monkeypatch.setattr(commands_module, "require_admin", AsyncMock(return_value=True))
    context.application.bot_data["user_service"].list_recent.return_value = []

    await cmd_users(update, context)

    update.effective_message.reply_text.assert_awaited_once_with("No users recorded yet.")


@pytest.mark.asyncio
async def test_cmd_users_formats_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    context = _ctx()
    monkeypatch.setattr(commands_module, "require_admin", AsyncMock(return_value=True))
    context.application.bot_data["user_service"].list_recent.return_value = [
        make_user(telegram_id=1, username="a"),
        make_user(
            telegram_id=2,
            username=None,
            first_name="B",
            last_name="C",
            is_allowed=False,
            last_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    ]

    await cmd_users(update, context)

    text = update.effective_message.reply_text.await_args.args[0]
    assert "1 - @a - allowed" in text
    assert "2 - B C - blocked - UTC - last seen 2026-01-01 00:00 UTC" in text


@pytest.mark.asyncio
async def test_cmd_timezone_missing_user_or_message_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = AsyncMock(return_value=make_user())
    monkeypatch.setattr(common_module, "record_user_seen", seen)

    await cmd_timezone(_update(with_user=False), _ctx())
    await cmd_timezone(_update(with_message=False), _ctx())

    seen.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_timezone_access_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=False)))

    await cmd_timezone(update, _ctx(["UTC"]))

    assert "private" in update.effective_message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_timezone_current_shows_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(timezone=None)))

    await cmd_timezone(update, _ctx([]))

    assert "Europe/Warsaw" in update.effective_message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_timezone_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    context = _ctx(["Bad/Zone"])
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user()))
    context.application.bot_data["user_service"].set_timezone.side_effect = ValueError("bad")

    await cmd_timezone(update, context)

    assert "recognize" in update.effective_message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_timezone_updated(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    context = _ctx(["Europe/Moscow"])
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user()))
    context.application.bot_data["user_service"].set_timezone.return_value = make_user(timezone="Europe/Moscow")

    await cmd_timezone(update, context)

    context.application.bot_data["user_service"].set_timezone.assert_awaited_once_with(123, "Europe/Moscow")
    assert "Europe/Moscow" in update.effective_message.reply_text.await_args.args[0]
