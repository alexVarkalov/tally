"""/stats and the stats:<YYYY-MM> callback (requirements §4.4). One message for all active trackers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from tally.handlers.callbacks import authorized_query
from tally.handlers.common import edit_message, require_access, show_menu, user_now
from tally.handlers.errors import report_error
from tally.handlers.menu import stats_keyboard
from tally.i18n import t
from tally.services import StatsService, TrackerDays, TrackerService, render_month
from tally.services.dates import parse_month_key
from tally.sheets import SheetsError

logger = logging.getLogger(__name__)


async def build_stats(context: ContextTypes.DEFAULT_TYPE, year: int, month: int) -> str:
    """Fetch every active tracker's days and render the month; one unavailable worksheet never hides the others."""
    tracker_service: TrackerService = context.application.bot_data["tracker_service"]
    stats_service: StatsService = context.application.bot_data["stats_service"]
    items: list[TrackerDays] = []
    for tracker in await tracker_service.list_active():
        try:
            days: tuple | None = tuple(await stats_service.fetch_days(tracker))
        except SheetsError as exc:
            logger.exception("tracker %r: cannot read worksheet %r", tracker.key, tracker.worksheet)
            await report_error(context, exc)
            days = None
        items.append(TrackerDays(tracker.label, days))
    return render_month(year, month, items)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return

    user = await require_access(update, context)
    if user is None:
        return

    now = user_now(user, context.application.bot_data["settings"])
    current = (now.year, now.month)
    text = await build_stats(context, *current)
    await update.effective_message.reply_html(text, reply_markup=stats_keyboard(*current, current))


async def on_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    authorized = await authorized_query(update, context)
    if authorized is None:
        return
    query, user = authorized

    parsed = parse_month_key(query.data.split(":", maxsplit=1)[1])
    if parsed is None:
        await query.answer(t("invalid_date"), show_alert=True)
        await show_menu(query, context, user)
        return

    await query.answer()
    now = user_now(user, context.application.bot_data["settings"])
    text = await build_stats(context, *parsed)
    await edit_message(query, text, stats_keyboard(*parsed, (now.year, now.month)))
