from __future__ import annotations

import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from telegram.error import BadRequest

from tally.handlers import callbacks as callbacks_module
from tally.handlers import common as common_module
from tally.handlers.callbacks import authorized_query, on_menu, on_record
from tally.sheets import SheetsError
from tests.helpers import make_settings, make_tracker, make_user

NOW = datetime(2026, 9, 15, 10, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
MY = make_tracker(key="my", label="MY", worksheet="my-counter")
OUR = make_tracker(key="our", label="OUR", worksheet="our-counter", position=2)


def _ctx() -> SimpleNamespace:
    tracker_service = AsyncMock()
    tracker_service.list_active.return_value = [MY, OUR]
    tracker_service.get_active.side_effect = lambda key: {"my": MY, "our": OUR}.get(key)
    stats_service = AsyncMock()
    stats_service.fetch_days.return_value = [date(2026, 9, 15), date(2026, 9, 14), date(2026, 8, 1)]
    return SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "settings": make_settings(),
                "user_service": AsyncMock(),
                "tracker_service": tracker_service,
                "record_service": AsyncMock(),
                "stats_service": stats_service,
            }
        )
    )


def _update(data: str | None, with_query: bool = True) -> SimpleNamespace:
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        message=SimpleNamespace(reply_markup="ORIGINAL"),
    )
    return SimpleNamespace(
        callback_query=query if with_query else None,
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=123),
    )


def _grid(markup) -> list[list[tuple[str, str]]]:  # type: ignore[no-untyped-def]
    return [[(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard]


@pytest.fixture
def owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(username="alex")))
    monkeypatch.setattr(callbacks_module, "record_user_seen", AsyncMock(return_value=make_user(username="alex")))
    monkeypatch.setattr(callbacks_module, "user_now", lambda user, settings: NOW)
    monkeypatch.setattr(common_module, "user_now", lambda user, settings: NOW)


@pytest.mark.asyncio
async def test_authorized_query_without_query_or_user(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = AsyncMock(return_value=None)
    monkeypatch.setattr(callbacks_module, "record_user_seen", seen)

    assert await authorized_query(_update(None, with_query=False), _ctx()) is None
    assert await authorized_query(_update(None), _ctx()) is None
    seen.assert_not_awaited()
    assert await authorized_query(_update("rec:my"), _ctx()) is None


@pytest.mark.asyncio
async def test_callbacks_refuse_unknown_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(callbacks_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=False)))
    context = _ctx()

    for update in (_update("rec:my"), _update("rec:my:2026-09-15"), _update("menu:open")):
        await on_record(update, context) if update.callback_query.data.startswith("rec") else await on_menu(
            update, context
        )
        update.callback_query.answer.assert_awaited_once_with("Not allowed", show_alert=True)
        update.callback_query.edit_message_text.assert_not_awaited()

    context.application.bot_data["record_service"].record.assert_not_awaited()


@pytest.mark.asyncio
async def test_tracker_tap_shows_date_buttons_in_user_timezone(owner: None) -> None:
    update = _update("rec:my")
    context = _ctx()

    await on_record(update, context)

    query = update.callback_query
    query.answer.assert_awaited_once_with()
    text, kwargs = query.edit_message_text.await_args.args[0], query.edit_message_text.await_args.kwargs
    assert text == "Which day for <b>MY</b>?"
    assert kwargs["parse_mode"] == "HTML"
    assert _grid(kwargs["reply_markup"]) == [
        [
            ("Sun 13", "rec:my:2026-09-13"),
            ("Yesterday · Mon 14", "rec:my:2026-09-14"),
            ("Today · Tue 15", "rec:my:2026-09-15"),
        ],
        [("◀ Back", "menu:open")],
    ]


@pytest.mark.asyncio
async def test_date_tap_records_confirms_and_reattaches_menu(owner: None) -> None:
    update = _update("rec:my:2026-09-14")
    context = _ctx()

    await on_record(update, context)

    record = context.application.bot_data["record_service"].record
    record.assert_awaited_once()
    tracker, day, now, user = record.await_args.args
    assert (tracker.key, day, now, user.username) == ("my", date(2026, 9, 14), NOW, "alex")

    query = update.callback_query
    assert _grid(query.edit_message_reply_markup.await_args_list[0].kwargs["reply_markup"]) == [
        [("⏳ saving…", "menu:noop")]
    ]
    query.answer.assert_awaited_once_with()
    text = query.edit_message_text.await_args.args[0]
    assert text == "✅ MY · Mon 14 Sep 2026 recorded. September: 2 (that day: 1)"
    assert _grid(query.edit_message_text.await_args.kwargs["reply_markup"]) == [
        [("MY", "rec:my"), ("OUR", "rec:our")],
        [("📊 Stats", "stats:2026-09")],
    ]


@pytest.mark.asyncio
async def test_date_tap_write_failure_alerts_and_restores_keyboard(owner: None) -> None:
    update = _update("rec:my:2026-09-15")
    context = _ctx()
    context.application.bot_data["record_service"].record.side_effect = SheetsError("down")

    await on_record(update, context)

    query = update.callback_query
    query.answer.assert_awaited_once_with("Could not write, try again", show_alert=True)
    assert query.edit_message_reply_markup.await_args_list[-1].kwargs == {"reply_markup": "ORIGINAL"}
    query.edit_message_text.assert_not_awaited()
    context.application.bot_data["stats_service"].fetch_days.assert_not_awaited()


@pytest.mark.asyncio
async def test_date_tap_confirms_without_counts_when_readback_fails(owner: None) -> None:
    update = _update("rec:my:2026-09-15")
    context = _ctx()
    context.application.bot_data["stats_service"].fetch_days.side_effect = SheetsError("down")

    await on_record(update, context)

    assert update.callback_query.edit_message_text.await_args.args[0] == "✅ MY · Tue 15 Sep 2026 recorded."


@pytest.mark.asyncio
async def test_stale_tracker_and_invalid_date_alert_and_reshow_menu(owner: None) -> None:
    context = _ctx()

    for data, alert in (
        ("rec:gone", "That tracker is no longer available"),
        ("rec:gone:2026-09-15", "That tracker is no longer available"),
        ("rec:my:2026-13-45", "That date is not valid"),
        ("rec:", "That tracker is no longer available"),
    ):
        update = _update(data)
        await on_record(update, context)
        update.callback_query.answer.assert_awaited_once_with(alert, show_alert=True)
        assert update.callback_query.edit_message_text.await_args.args[0] == "What do you want to record?"

    context.application.bot_data["record_service"].record.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_tap_while_append_in_flight_is_ignored(owner: None) -> None:
    context = _ctx()
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_record(*_args: object) -> None:
        started.set()
        await release.wait()

    context.application.bot_data["record_service"].record.side_effect = slow_record
    first, second = _update("rec:my:2026-09-15"), _update("rec:my:2026-09-15")

    task = asyncio.create_task(on_record(first, context))
    await started.wait()
    await on_record(second, context)
    release.set()
    await task

    second.callback_query.answer.assert_awaited_once_with()
    second.callback_query.edit_message_reply_markup.assert_not_awaited()
    assert context.application.bot_data["record_service"].record.await_count == 1
    first.callback_query.edit_message_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_open_and_noop(owner: None) -> None:
    context = _ctx()

    update = _update("menu:open")
    await on_menu(update, context)
    update.callback_query.answer.assert_awaited_once_with()
    assert update.callback_query.edit_message_text.await_args.args[0] == "What do you want to record?"

    update = _update("menu:noop")
    await on_menu(update, context)
    update.callback_query.answer.assert_awaited_once_with()
    update.callback_query.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_unchanged_message_edit_is_not_an_error(owner: None) -> None:
    update = _update("menu:open")
    update.callback_query.edit_message_text.side_effect = BadRequest("Message is not modified")

    await on_menu(update, _ctx())

    update = _update("menu:open")
    update.callback_query.edit_message_text.side_effect = BadRequest("Chat not found")
    with pytest.raises(BadRequest):
        await on_menu(update, _ctx())
