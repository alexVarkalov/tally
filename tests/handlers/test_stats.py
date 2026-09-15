from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from tally.handlers import callbacks as callbacks_module
from tally.handlers import common as common_module
from tally.handlers import stats as stats_module
from tally.handlers.stats import build_stats, cmd_stats, on_stats
from tally.sheets import SheetsError
from tests.helpers import make_settings, make_tracker, make_user

NOW = datetime(2026, 9, 15, 10, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
MY = make_tracker(key="my", label="MY", worksheet="my-counter")
GYM = make_tracker(key="gym", label="Gym", worksheet="gym", position=2)


def _ctx() -> SimpleNamespace:
    tracker_service = AsyncMock()
    tracker_service.list_active.return_value = [MY, GYM]
    stats_service = AsyncMock()
    stats_service.fetch_days.side_effect = lambda tracker: {
        "my": [date(2026, 9, 15), date(2026, 9, 15), date(2026, 8, 3), date(2025, 1, 1)],
        "gym": [date(2026, 9, 1)],
    }[tracker.key]
    return SimpleNamespace(
        bot=AsyncMock(),
        application=SimpleNamespace(
            bot_data={
                "settings": make_settings(),
                "user_service": AsyncMock(),
                "tracker_service": tracker_service,
                "stats_service": stats_service,
            }
        ),
    )


def _grid(markup) -> list[list[tuple[str, str]]]:  # type: ignore[no-untyped-def]
    return [[(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard]


@pytest.fixture
def owner(monkeypatch: pytest.MonkeyPatch) -> None:
    user = make_user(username="alex")
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=user))
    monkeypatch.setattr(callbacks_module, "record_user_seen", AsyncMock(return_value=user))
    for module in (common_module, callbacks_module, stats_module):
        monkeypatch.setattr(module, "user_now", lambda user, settings: NOW)


@pytest.mark.asyncio
async def test_build_stats_renders_every_tracker_and_marks_unavailable(owner: None) -> None:
    context = _ctx()
    fetch = context.application.bot_data["stats_service"].fetch_days
    fetch.side_effect = lambda tracker: (
        [date(2026, 9, 15)] if tracker.key == "my" else (_ for _ in ()).throw(SheetsError("WorksheetNotFound: gym"))
    )

    text = await build_stats(context, 2026, 9)

    assert "<b>MY</b> — 1" in text
    assert "<b>Gym</b> — ⚠ unavailable" in text
    assert text.endswith("Year 2026: MY 1 · Gym ⚠")
    context.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_stats_current_month_with_navigation(owner: None) -> None:
    message = SimpleNamespace(reply_text=AsyncMock(), reply_html=AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=123), effective_message=message)

    await cmd_stats(update, _ctx())

    text = message.reply_html.await_args.args[0]
    assert text.startswith("📊 <b>September 2026</b>")
    assert "<b>MY</b> — 2\n  Tue 15 · 2" in text
    assert "<b>Gym</b> — 1\n  Tue 1 · 1" in text
    assert text.endswith("Year 2026: MY 3 · Gym 1")
    assert _grid(message.reply_html.await_args.kwargs["reply_markup"]) == [
        [("◀ Aug 2026", "stats:2026-08")],
        [("Menu", "menu:open")],
    ]


@pytest.mark.asyncio
async def test_cmd_stats_no_message_or_no_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=False)))
    message = SimpleNamespace(reply_text=AsyncMock(), reply_html=AsyncMock())

    await cmd_stats(SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=None), _ctx())
    await cmd_stats(SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message), _ctx())

    message.reply_html.assert_not_awaited()
    message.reply_text.assert_awaited_once_with("This is a private bot.")


def _query_update(data: str) -> SimpleNamespace:
    query = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_text=AsyncMock())
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123), effective_chat=None)


@pytest.mark.asyncio
async def test_on_stats_navigates_to_a_past_month(owner: None) -> None:
    update = _query_update("stats:2026-08")

    await on_stats(update, _ctx())

    query = update.callback_query
    query.answer.assert_awaited_once_with()
    text = query.edit_message_text.await_args.args[0]
    assert text.startswith("📊 <b>August 2026</b>")
    assert "<b>MY</b> — 1\n  Mon 3 · 1" in text
    assert _grid(query.edit_message_text.await_args.kwargs["reply_markup"]) == [
        [("◀ Jul 2026", "stats:2026-07"), ("Sep 2026 ▶", "stats:2026-09")],
        [("Menu", "menu:open")],
    ]


@pytest.mark.asyncio
async def test_on_stats_invalid_month_reshows_menu(owner: None) -> None:
    update = _query_update("stats:garbage")

    await on_stats(update, _ctx())

    update.callback_query.answer.assert_awaited_once_with("That date is not valid", show_alert=True)
    assert update.callback_query.edit_message_text.await_args.args[0] == "What do you want to record?"


@pytest.mark.asyncio
async def test_on_stats_refuses_unknown_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(callbacks_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=False)))
    update = _query_update("stats:2026-09")

    await on_stats(update, _ctx())

    update.callback_query.answer.assert_awaited_once_with("Not allowed", show_alert=True)
    update.callback_query.edit_message_text.assert_not_awaited()
