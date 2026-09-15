from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from tally.handlers import common as common_module
from tally.handlers import trackers as trackers_module
from tally.handlers.trackers import (
    cmd_archive,
    cmd_attach,
    cmd_detach,
    cmd_new,
    cmd_rename,
    cmd_trackers,
    cmd_unarchive,
)
from tally.services import TrackerError
from tally.sheets import SheetsError
from tests.helpers import make_settings, make_tracker, make_user

NOW = datetime(2026, 9, 15, 10, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
MY = make_tracker(key="my", label="MY", worksheet="my-counter")
OUR = make_tracker(key="our", label="OUR", worksheet="our-counter", position=2)
OLD = make_tracker(key="old", label="Old", worksheet="old", position=3, archived_at=datetime(2026, 1, 1, tzinfo=UTC))


def _fetch_days(tracker) -> list[date]:  # type: ignore[no-untyped-def]
    days = {"my": [date(2026, 9, 15), date(2026, 9, 13), date(2025, 3, 3)], "old": []}
    if tracker.key not in days:
        raise SheetsError(f"WorksheetNotFound: {tracker.worksheet}")
    return days[tracker.key]


def _ctx(args: list[str] | None = None) -> SimpleNamespace:
    tracker_service = AsyncMock()
    tracker_service.list_all.return_value = [MY, OUR, OLD]
    stats_service = AsyncMock()
    stats_service.fetch_days.side_effect = _fetch_days
    return SimpleNamespace(
        args=list(args or []),
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


def _update(with_message: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_message=SimpleNamespace(reply_text=AsyncMock()) if with_message else None,
    )


def _reply(update: SimpleNamespace) -> str:
    return update.effective_message.reply_text.await_args.args[0]


@pytest.fixture
def owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user()))
    monkeypatch.setattr(trackers_module, "user_now", lambda user, settings: NOW)


ALL_COMMANDS = (cmd_trackers, cmd_new, cmd_attach, cmd_rename, cmd_archive, cmd_unarchive, cmd_detach)


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ALL_COMMANDS)
async def test_commands_ignore_missing_message_and_refuse_outsiders(  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch, command
) -> None:
    monkeypatch.setattr(common_module, "record_user_seen", AsyncMock(return_value=make_user(is_allowed=False)))
    context = _ctx(["my", "x"])

    await command(_update(with_message=False), context)
    update = _update()
    await command(update, context)

    assert _reply(update) == "This is a private bot."
    service = context.application.bot_data["tracker_service"]
    for method in ("create", "attach", "rename", "archive", "unarchive", "detach"):
        getattr(service, method).assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_trackers_lists_counts_archived_and_warnings(owner: None) -> None:
    update = _update()

    await cmd_trackers(update, _ctx())

    assert _reply(update) == (
        "MY (my, my-counter) · Sep: 2 · total 3\n"
        "⚠ OUR (our, our-counter) · unavailable: WorksheetNotFound: our-counter\n"
        "\n"
        "Archived:\n"
        "Old (old, old) · Sep: 0 · total 0"
    )


@pytest.mark.asyncio
async def test_cmd_trackers_empty_registry(owner: None) -> None:
    update = _update()
    context = _ctx()
    context.application.bot_data["tracker_service"].list_all.return_value = []

    await cmd_trackers(update, context)

    assert "/new" in _reply(update) and "/attach" in _reply(update)


@pytest.mark.asyncio
async def test_cmd_new_creates_with_optional_label(owner: None) -> None:
    context = _ctx(["gym", "🏋️", "Gym"])
    context.application.bot_data["tracker_service"].create.return_value = make_tracker(
        key="gym", label="🏋️ Gym", worksheet="gym"
    )
    update = _update()

    await cmd_new(update, context)

    context.application.bot_data["tracker_service"].create.assert_awaited_once_with("gym", "🏋️ Gym")
    assert _reply(update) == "Created 🏋️ Gym (gym, worksheet 'gym')."

    context = _ctx(["gym"])
    await cmd_new(_update(), context)
    context.application.bot_data["tracker_service"].create.assert_awaited_once_with("gym", None)


@pytest.mark.asyncio
async def test_cmd_new_usage_and_errors(owner: None) -> None:
    update = _update()
    await cmd_new(update, _ctx([]))
    assert _reply(update) == "Usage: /new <key> [label]"

    context = _ctx(["gym"])
    context.application.bot_data["tracker_service"].create.side_effect = TrackerError("Tracker 'gym' already exists")
    update = _update()
    await cmd_new(update, context)
    assert _reply(update) == "Tracker 'gym' already exists"

    context = _ctx(["gym"])
    context.application.bot_data["tracker_service"].create.side_effect = SheetsError("APIError: 503")
    update = _update()
    await cmd_new(update, context)
    assert _reply(update) == "Google Sheets error: APIError: 503"
    context.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_attach(owner: None) -> None:
    context = _ctx(["my", "my-counter", "MY"])
    context.application.bot_data["tracker_service"].attach.return_value = MY
    update = _update()

    await cmd_attach(update, context)

    context.application.bot_data["tracker_service"].attach.assert_awaited_once_with("my", "my-counter", "MY")
    assert _reply(update) == "Attached MY (my, worksheet 'my-counter')."

    update = _update()
    await cmd_attach(update, _ctx(["my"]))
    assert _reply(update) == "Usage: /attach <key> <worksheet> [label]"

    context = _ctx(["x", "users"])
    context.application.bot_data["tracker_service"].attach.side_effect = TrackerError(
        "Worksheet 'users' header is id | username; expected Year | Month | Day | Created at | Username | Comment"
    )
    update = _update()
    await cmd_attach(update, context)
    assert "id | username" in _reply(update)


@pytest.mark.asyncio
async def test_cmd_rename(owner: None) -> None:
    context = _ctx(["gym", "Gym", "time"])
    context.application.bot_data["tracker_service"].rename.return_value = make_tracker(key="gym", label="Gym time")
    update = _update()

    await cmd_rename(update, context)

    context.application.bot_data["tracker_service"].rename.assert_awaited_once_with("gym", "Gym time")
    assert _reply(update).startswith("Renamed Gym time (gym")

    update = _update()
    await cmd_rename(update, _ctx(["gym"]))
    assert _reply(update) == "Usage: /rename <key> <label>"


@pytest.mark.asyncio
async def test_cmd_archive_and_unarchive(owner: None) -> None:
    context = _ctx(["our"])
    service = context.application.bot_data["tracker_service"]
    service.archive.return_value = OUR
    service.unarchive.return_value = OUR
    update = _update()

    await cmd_archive(update, context)
    assert _reply(update) == "Archived OUR (our, worksheet 'our-counter')."
    update = _update()
    await cmd_unarchive(update, context)
    assert _reply(update) == "Unarchived OUR (our, worksheet 'our-counter')."

    service.archive.assert_awaited_once_with("our")
    service.unarchive.assert_awaited_once_with("our")

    update = _update()
    await cmd_archive(update, _ctx([]))
    assert _reply(update) == "Usage: /archive <key>"
    update = _update()
    await cmd_unarchive(update, _ctx([]))
    assert _reply(update) == "Usage: /unarchive <key>"


@pytest.mark.asyncio
async def test_cmd_detach_requires_exact_confirmation(owner: None) -> None:
    for args in (["gym"], ["gym", "yes"], ["gym", "confirm", "extra"]):
        context = _ctx(args)
        update = _update()
        await cmd_detach(update, context)
        assert "/detach gym confirm" in _reply(update)
        context.application.bot_data["tracker_service"].detach.assert_not_awaited()

    update = _update()
    await cmd_detach(update, _ctx([]))
    assert _reply(update) == "Usage: /detach <key> confirm"

    context = _ctx(["gym", "confirm"])
    context.application.bot_data["tracker_service"].detach.return_value = make_tracker(
        key="gym", label="Gym", worksheet="gym"
    )
    update = _update()
    await cmd_detach(update, context)
    context.application.bot_data["tracker_service"].detach.assert_awaited_once_with("gym")
    assert _reply(update) == "Detached Gym (gym, worksheet 'gym'). Worksheet kept."
