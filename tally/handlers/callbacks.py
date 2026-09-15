"""Callback queries: `rec:` (the recording flow, requirements §4.2) and `menu:`. One handler per prefix."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes

from tally.config import Settings
from tally.handlers.common import edit_message, record_user_seen, show_menu, user_has_access, user_now
from tally.handlers.menu import choose_day_text, date_keyboard, saving_keyboard, tracker_menu_keyboard
from tally.i18n import t
from tally.persistence import BotUser
from tally.services import (
    RecordService,
    StatsService,
    TrackerService,
    date_choices,
    month_summary,
    render_confirmation,
)
from tally.sheets import SheetsError

logger = logging.getLogger(__name__)

_LOCKS_KEY = "record_locks"


async def authorized_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[CallbackQuery, BotUser] | None:
    """The callback query and its user when the user may use the bot; answers "Not allowed" otherwise."""
    query = update.callback_query
    if query is None or query.data is None:
        return None

    user = await record_user_seen(update, context)
    if user is None:
        return None
    settings: Settings = context.application.bot_data["settings"]
    if not user_has_access(user, settings):
        await query.answer(t("not_allowed"), show_alert=True)
        return None
    return query, user


async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    authorized = await authorized_query(update, context)
    if authorized is None:
        return
    query, user = authorized

    await query.answer()
    action = query.data.split(":", maxsplit=1)[1]
    if action == "open":
        await show_menu(query, context, user)


async def on_record(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    authorized = await authorized_query(update, context)
    if authorized is None:
        return
    query, user = authorized

    parts = query.data.split(":", maxsplit=2)
    key = parts[1] if len(parts) > 1 else ""
    tracker_service: TrackerService = context.application.bot_data["tracker_service"]
    tracker = await tracker_service.get_active(key)
    if tracker is None:
        await _stale(query, context, user, t("stale_tracker"))
        return

    settings: Settings = context.application.bot_data["settings"]
    now = user_now(user, settings)
    if len(parts) == 2:
        await query.answer()
        choices = date_choices(now.date(), settings.day_choices)
        await edit_message(query, choose_day_text(tracker), date_keyboard(tracker.key, choices, now.date()))
        return

    try:
        day = date.fromisoformat(parts[2])
    except ValueError:
        await _stale(query, context, user, t("invalid_date"))
        return

    lock = _chat_lock(update, context)
    if lock.locked():
        # A second tap on the same message while the first append is in flight: never write twice.
        await query.answer()
        return

    async with lock:
        original_markup = getattr(query.message, "reply_markup", None)
        await query.edit_message_reply_markup(reply_markup=saving_keyboard())
        record_service: RecordService = context.application.bot_data["record_service"]
        try:
            await record_service.record(tracker, day, now, user)
        except SheetsError:
            logger.exception("could not append to %r for tracker %r", tracker.worksheet, tracker.key)
            await query.answer(t("write_failed"), show_alert=True)
            await query.edit_message_reply_markup(reply_markup=original_markup)
            return

        await query.answer()
        stats_service: StatsService = context.application.bot_data["stats_service"]
        try:
            summary = month_summary(await stats_service.fetch_days(tracker), day.year, day.month)
        except SheetsError:
            logger.exception("row appended but could not read %r back for the summary", tracker.worksheet)
            summary = None

        trackers = await tracker_service.list_active()
        await edit_message(
            query,
            render_confirmation(tracker.label, day, summary),
            tracker_menu_keyboard(trackers, (now.year, now.month)),
        )


async def _stale(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, user: BotUser, text: str) -> None:
    await query.answer(text, show_alert=True)
    await show_menu(query, context, user)


def _chat_lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> asyncio.Lock:
    locks: dict[int, asyncio.Lock] = context.application.bot_data.setdefault(_LOCKS_KEY, {})
    chat_id = update.effective_chat.id if update.effective_chat is not None else update.effective_user.id
    return locks.setdefault(chat_id, asyncio.Lock())
