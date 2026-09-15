"""Keyboard and text builders for the recording flow and the stats view. Pure: no I/O, unit-tested directly."""

from __future__ import annotations

import html
from collections.abc import Sequence
from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from tally.i18n import t
from tally.persistence import Tracker
from tally.services.dates import format_day, month_key, month_short_title, next_month, prev_month

TRACKERS_PER_ROW = 2


def tracker_menu_text(trackers: Sequence[Tracker]) -> str:
    return t("menu_title") if trackers else t("menu_empty")


def tracker_menu_keyboard(trackers: Sequence[Tracker], stats_month: tuple[int, int]) -> InlineKeyboardMarkup:
    """One button per active tracker in position order, two per row; `📊 Stats` for the given month last."""
    buttons = [InlineKeyboardButton(tracker.label, callback_data=f"rec:{tracker.key}") for tracker in trackers]
    rows = [buttons[i : i + TRACKERS_PER_ROW] for i in range(0, len(buttons), TRACKERS_PER_ROW)]
    rows.append([InlineKeyboardButton(t("button_stats"), callback_data=f"stats:{month_key(*stats_month)}")])
    return InlineKeyboardMarkup(rows)


def date_label(day: date, today: date) -> str:
    if day == today:
        return t("button_today", day=format_day(day))
    if day == today - timedelta(days=1):
        return t("button_yesterday", day=format_day(day))
    return format_day(day)


def choose_day_text(tracker: Tracker) -> str:
    return t("choose_day", label=html.escape(tracker.label))


def date_keyboard(tracker_key: str, choices: Sequence[date], today: date) -> InlineKeyboardMarkup:
    """One row of date buttons (oldest first, today last) carrying the ISO date, then `◀ Back`."""
    row = [
        InlineKeyboardButton(date_label(day, today), callback_data=f"rec:{tracker_key}:{day.isoformat()}")
        for day in choices
    ]
    return InlineKeyboardMarkup([row, [InlineKeyboardButton(t("button_back"), callback_data="menu:open")]])


def saving_keyboard() -> InlineKeyboardMarkup:
    """Placeholder shown while an append is in flight, so a second tap has nothing to hit."""
    return InlineKeyboardMarkup([[InlineKeyboardButton(t("button_saving"), callback_data="menu:noop")]])


def stats_keyboard(year: int, month: int, current: tuple[int, int]) -> InlineKeyboardMarkup:
    """`◀ Aug 2026` · `Oct 2026 ▶` (next only before the current month), then `Menu`."""
    previous = prev_month(year, month)
    navigation = [
        InlineKeyboardButton(
            t("button_prev_month", month=month_short_title(*previous)), callback_data=f"stats:{month_key(*previous)}"
        )
    ]
    if (year, month) != current:
        following = next_month(year, month)
        navigation.append(
            InlineKeyboardButton(
                t("button_next_month", month=month_short_title(*following)),
                callback_data=f"stats:{month_key(*following)}",
            )
        )
    return InlineKeyboardMarkup([navigation, [InlineKeyboardButton(t("button_menu"), callback_data="menu:open")]])
