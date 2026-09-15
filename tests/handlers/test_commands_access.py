from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tally.handlers import commands as commands_module
from tally.handlers.commands import _set_user_access, cmd_allow_user, cmd_block_user
from tests.helpers import make_settings, make_user


def _context(args: list[str], admin_ids: frozenset[int] = frozenset()) -> SimpleNamespace:
    return SimpleNamespace(
        args=args,
        application=SimpleNamespace(
            bot_data={"settings": make_settings(admin_user_ids=admin_ids), "user_service": AsyncMock()}
        ),
    )


def _update() -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=500),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_set_user_access_requires_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(commands_module, "require_admin", AsyncMock(return_value=False))

    await _set_user_access(update, _context(["1"]), allowed=True)

    update.effective_message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_user_access_replies_usage_for_invalid_target(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    monkeypatch.setattr(commands_module, "require_admin", AsyncMock(return_value=True))

    await _set_user_access(update, _context(["bad"]), allowed=True)

    update.effective_message.reply_text.assert_awaited_once_with("Usage: /allow_user <telegram_user_id>")


@pytest.mark.asyncio
async def test_set_user_access_prevents_blocking_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    context = _context(["42"], admin_ids=frozenset({42}))
    monkeypatch.setattr(commands_module, "require_admin", AsyncMock(return_value=True))

    await _set_user_access(update, context, allowed=False)

    update.effective_message.reply_text.assert_awaited_once()
    context.application.bot_data["user_service"].set_allowed.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_user_access_updates_user(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    context = _context(["42"])
    monkeypatch.setattr(commands_module, "require_admin", AsyncMock(return_value=True))
    context.application.bot_data["user_service"].set_allowed.return_value = make_user(telegram_id=42, is_allowed=True)

    await _set_user_access(update, context, allowed=True)

    context.application.bot_data["user_service"].set_allowed.assert_awaited_once_with(42, True)
    update.effective_message.reply_text.assert_awaited_once_with("User 42 is now allowed.")


@pytest.mark.asyncio
async def test_allow_and_block_delegate_to_shared_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    update = _update()
    context = _context(["42"])
    helper = AsyncMock()
    monkeypatch.setattr(commands_module, "_set_user_access", helper)

    await cmd_allow_user(update, context)
    await cmd_block_user(update, context)

    assert helper.await_args_list[0].kwargs == {"allowed": True}
    assert helper.await_args_list[1].kwargs == {"allowed": False}
