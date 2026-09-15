"""Tracker management commands (requirements §4.3). Plain, short English replies, admin-style."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from tally.handlers.common import require_access, user_now
from tally.handlers.errors import report_error
from tally.persistence import Tracker
from tally.services import StatsService, TrackerError, TrackerService, month_summary
from tally.services.dates import month_abbr
from tally.sheets import SheetsError

logger = logging.getLogger(__name__)

DETACH_CONFIRMATION = "confirm"


async def cmd_trackers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One line per tracker with this month's and the total row count; ⚠ when the worksheet is unusable."""
    if update.effective_message is None:
        return
    user = await require_access(update, context)
    if user is None:
        return

    tracker_service: TrackerService = context.application.bot_data["tracker_service"]
    trackers = await tracker_service.list_all()
    if not trackers:
        await update.effective_message.reply_text(
            "No trackers. Use /new <key> [label] or /attach <key> <worksheet> [label]."
        )
        return

    now = user_now(user, context.application.bot_data["settings"])
    active = [tracker for tracker in trackers if tracker.is_active]
    archived = [tracker for tracker in trackers if not tracker.is_active]
    lines = [await _tracker_line(context, tracker, now.year, now.month) for tracker in active] or [
        "(no active trackers)"
    ]
    if archived:
        lines.append("")
        lines.append("Archived:")
        lines.extend([await _tracker_line(context, tracker, now.year, now.month) for tracker in archived])
    await update.effective_message.reply_text("\n".join(lines))


async def _tracker_line(context: ContextTypes.DEFAULT_TYPE, tracker: Tracker, year: int, month: int) -> str:
    stats_service: StatsService = context.application.bot_data["stats_service"]
    head = f"{tracker.label} ({tracker.key}, {tracker.worksheet})"
    try:
        days = await stats_service.fetch_days(tracker)
    except SheetsError as exc:
        logger.warning("tracker %r: worksheet %r unavailable: %s", tracker.key, tracker.worksheet, exc)
        return f"⚠ {head} · unavailable: {exc}"
    return f"{head} · {month_abbr(month)}: {month_summary(days, year, month).total} · total {len(days)}"


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None or await require_access(update, context) is None:
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /new <key> [label]")
        return

    tracker_service: TrackerService = context.application.bot_data["tracker_service"]
    await _reply_result(
        update,
        context,
        tracker_service.create(args[0], " ".join(args[1:]) or None),
        lambda t: f"Created {_describe(t)}.",
    )


async def cmd_attach(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None or await require_access(update, context) is None:
        return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /attach <key> <worksheet> [label]")
        return

    tracker_service: TrackerService = context.application.bot_data["tracker_service"]
    await _reply_result(
        update,
        context,
        tracker_service.attach(args[0], args[1], " ".join(args[2:]) or None),
        lambda t: f"Attached {_describe(t)}.",
    )


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None or await require_access(update, context) is None:
        return
    args = context.args or []
    if len(args) < 2:
        await update.effective_message.reply_text("Usage: /rename <key> <label>")
        return

    tracker_service: TrackerService = context.application.bot_data["tracker_service"]
    await _reply_result(
        update, context, tracker_service.rename(args[0], " ".join(args[1:])), lambda t: f"Renamed {_describe(t)}."
    )


async def cmd_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _archive(update, context, archived=True)


async def cmd_unarchive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _archive(update, context, archived=False)


async def _archive(update: Update, context: ContextTypes.DEFAULT_TYPE, *, archived: bool) -> None:
    if update.effective_message is None or await require_access(update, context) is None:
        return
    command = "archive" if archived else "unarchive"
    args = context.args or []
    if not args:
        await update.effective_message.reply_text(f"Usage: /{command} <key>")
        return

    tracker_service: TrackerService = context.application.bot_data["tracker_service"]
    operation = tracker_service.archive(args[0]) if archived else tracker_service.unarchive(args[0])
    await _reply_result(update, context, operation, lambda t: f"{command.capitalize()}d {_describe(t)}.")


async def cmd_detach(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registry only, and only with the exact confirmation `/detach <key> confirm`."""
    if update.effective_message is None or await require_access(update, context) is None:
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Usage: /detach <key> confirm")
        return
    if len(args) != 2 or args[1] != DETACH_CONFIRMATION:
        await update.effective_message.reply_text(
            f"This removes tracker {args[0]!r} from the registry; the worksheet is not touched and /attach "
            f"brings it back. To confirm send: /detach {args[0]} confirm"
        )
        return

    tracker_service: TrackerService = context.application.bot_data["tracker_service"]
    await _reply_result(
        update, context, tracker_service.detach(args[0]), lambda t: f"Detached {_describe(t)}. Worksheet kept."
    )


def _describe(tracker: Tracker) -> str:
    return f"{tracker.label} ({tracker.key}, worksheet {tracker.worksheet!r})"


async def _reply_result(update, context, operation, success) -> None:  # type: ignore[no-untyped-def]
    try:
        tracker = await operation
    except TrackerError as exc:
        await update.effective_message.reply_text(str(exc))
        return
    except SheetsError as exc:
        logger.exception("tracker command failed on Google Sheets")
        await update.effective_message.reply_text(f"Google Sheets error: {exc}")
        await report_error(context, exc)
        return
    await update.effective_message.reply_text(success(tracker))
