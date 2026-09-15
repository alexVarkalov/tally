"""Global PTB error handler: log every unhandled exception and ping the admins, rate-limited per error class."""

from __future__ import annotations

import html
import logging
from datetime import UTC, datetime, timedelta

from telegram.ext import ContextTypes

from tally.config import Settings

logger = logging.getLogger(__name__)

NOTIFY_COOLDOWN = timedelta(minutes=10)
_NOTIFIED_KEY = "error_notified_at"


def should_notify(last_sent: datetime | None, now: datetime, cooldown: timedelta = NOTIFY_COOLDOWN) -> bool:
    return last_sent is None or now - last_sent >= cooldown


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    logger.error("unhandled exception while processing %r", update, exc_info=error)
    if error is None:
        return

    settings: Settings | None = context.application.bot_data.get("settings")
    if settings is None or not settings.admin_user_ids:
        return

    key = type(error).__name__
    notified: dict[str, datetime] = context.application.bot_data.setdefault(_NOTIFIED_KEY, {})
    now = datetime.now(tz=UTC)
    if not should_notify(notified.get(key), now):
        return
    notified[key] = now

    text = f"⚠️ <b>{html.escape(key)}</b>\n<code>{html.escape(str(error)[:500])}</code>"
    for admin_id in settings.admin_user_ids:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        except Exception:
            logger.exception("failed to notify admin %s about %s", admin_id, key)
