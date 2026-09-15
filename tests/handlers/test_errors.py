from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tally.handlers.errors import NOTIFY_COOLDOWN, on_error, report_error, should_notify
from tests.helpers import make_settings


def test_should_notify_respects_cooldown() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    assert should_notify(None, now) is True
    assert should_notify(now - timedelta(minutes=1), now) is False
    assert should_notify(now - NOTIFY_COOLDOWN, now) is True


def _ctx(error: Exception | None, admins: frozenset[int] = frozenset({1, 2})) -> SimpleNamespace:
    return SimpleNamespace(
        error=error,
        bot=AsyncMock(),
        application=SimpleNamespace(bot_data={"settings": make_settings(admin_user_ids=admins)}),
    )


@pytest.mark.asyncio
async def test_on_error_notifies_each_admin_once_per_error_class() -> None:
    context = _ctx(RuntimeError("boom <b>"))

    await on_error(object(), context)
    await on_error(object(), context)
    await on_error(object(), _ctx(ValueError("other")))

    assert context.bot.send_message.await_count == 2
    kwargs = context.bot.send_message.await_args_list[0].kwargs
    assert kwargs["chat_id"] in {1, 2}
    assert "RuntimeError" in kwargs["text"]
    assert "&lt;b&gt;" in kwargs["text"]


@pytest.mark.asyncio
async def test_on_error_without_admins_or_error_is_silent() -> None:
    context = _ctx(RuntimeError("boom"), admins=frozenset())
    await on_error(object(), context)
    context.bot.send_message.assert_not_awaited()

    context = _ctx(None)
    await on_error(object(), context)
    context.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_error_survives_send_failure() -> None:
    context = _ctx(RuntimeError("boom"))
    context.bot.send_message.side_effect = RuntimeError("blocked")

    await on_error(object(), context)

    assert context.bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_report_error_shares_the_cooldown_with_on_error() -> None:
    context = _ctx(RuntimeError("boom"))

    await report_error(context, RuntimeError("first"))
    await on_error(object(), context)
    await report_error(context, ValueError("other"))

    assert context.bot.send_message.await_count == 4
    assert "first" in context.bot.send_message.await_args_list[0].kwargs["text"]
