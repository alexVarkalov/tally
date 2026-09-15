from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from tally.config import Settings
from tally.handlers.common import (
    format_user_datetime,
    format_user_display,
    format_user_timezone,
    parse_target_user_id,
    require_access,
    require_admin,
)
from tally.i18n import t
from tally.services import UserService


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return

    user = await require_access(update, context)
    if user is None:
        return

    await update.effective_message.reply_html(t("help_intro"))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return

    user = await require_access(update, context)
    if user is None:
        return

    await update.effective_message.reply_html("\n\n".join([t("help_intro"), t("help_commands")]))


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_admin(update, context):
        return

    settings: Settings = context.application.bot_data["settings"]
    user_service: UserService = context.application.bot_data["user_service"]
    users = await user_service.list_recent(limit=50)
    if not users:
        await update.effective_message.reply_text("No users recorded yet.")
        return

    lines = ["Recent users:"]
    for user in users:
        status = "allowed" if user.is_allowed else "blocked"
        display = format_user_display(user)
        timezone = format_user_timezone(user, settings)
        last_seen = format_user_datetime(user.last_seen_at, user, settings)
        lines.append(f"{user.telegram_id} - {display} - {status} - {timezone} - last seen {last_seen}")

    await update.effective_message.reply_text("\n".join(lines))


async def cmd_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_message is None:
        return

    user = await require_access(update, context)
    if user is None:
        return
    settings: Settings = context.application.bot_data["settings"]

    if not context.args:
        await update.effective_message.reply_text(t("timezone_current", timezone=format_user_timezone(user, settings)))
        return

    timezone = context.args[0].strip()
    user_service: UserService = context.application.bot_data["user_service"]
    try:
        updated_user = await user_service.set_timezone(update.effective_user.id, timezone)
    except ValueError:
        await update.effective_message.reply_text(t("timezone_invalid"))
        return

    await update.effective_message.reply_text(
        t("timezone_updated", timezone=format_user_timezone(updated_user, settings))
    )


async def cmd_allow_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_user_access(update, context, allowed=True)


async def cmd_block_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_user_access(update, context, allowed=False)


async def _set_user_access(update: Update, context: ContextTypes.DEFAULT_TYPE, *, allowed: bool) -> None:
    if not await require_admin(update, context):
        return

    if update.effective_message is None:
        return

    target_id = parse_target_user_id(context.args)
    if target_id is None:
        command = "allow_user" if allowed else "block_user"
        await update.effective_message.reply_text(f"Usage: /{command} <telegram_user_id>")
        return

    settings: Settings = context.application.bot_data["settings"]
    if not allowed and target_id in settings.admin_user_ids:
        await update.effective_message.reply_text(
            "Admin users cannot be blocked while they are listed in ADMIN_USER_IDS."
        )
        return

    user_service: UserService = context.application.bot_data["user_service"]
    user = await user_service.set_allowed(target_id, allowed)
    status = "allowed" if user.is_allowed else "blocked"
    await update.effective_message.reply_text(f"User {user.telegram_id} is now {status}.")
