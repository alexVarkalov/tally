from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import CallbackQuery, InlineKeyboardMarkup, Message, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from tally.config import Settings
from tally.handlers.menu import tracker_menu_keyboard, tracker_menu_text
from tally.i18n import t
from tally.persistence import BotUser, Tracker
from tally.services import TrackerService, UserService, resolve_timezone
from tally.services import user_has_access as _user_has_access


def user_timezone(user: BotUser, settings: Settings) -> ZoneInfo:
    return resolve_timezone(user.timezone or settings.default_timezone)


def format_user_datetime(when: datetime, user: BotUser, settings: Settings) -> str:
    timezone = user_timezone(user, settings)
    return when.astimezone(timezone).strftime(f"%Y-%m-%d %H:%M {timezone.key}")


def format_user_timezone(user: BotUser, settings: Settings) -> str:
    return user.timezone or settings.default_timezone


async def record_user_seen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotUser | None:
    telegram_user = update.effective_user
    if telegram_user is None:
        return None

    user_service: UserService = context.application.bot_data["user_service"]
    return await user_service.record_seen(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
        language_code=telegram_user.language_code,
    )


def user_has_access(user: BotUser, settings: Settings) -> bool:
    return _user_has_access(user, settings.admin_user_ids)


async def require_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotUser | None:
    """Record the user and return it when it may use the bot; reply "private bot" and return None otherwise."""
    if update.effective_user is None or update.effective_message is None:
        return None

    user = await record_user_seen(update, context)
    if user is None:
        return None
    settings: Settings = context.application.bot_data["settings"]
    if not user_has_access(user, settings):
        await update.effective_message.reply_text(t("private_bot"))
        return None
    return user


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_user is None or update.effective_message is None:
        return False

    await record_user_seen(update, context)
    settings: Settings = context.application.bot_data["settings"]
    if update.effective_user.id in settings.admin_user_ids:
        return True

    await update.effective_message.reply_text(t("admin_only"))
    return False


def parse_target_user_id(args: list[str] | tuple[str, ...] | None) -> int | None:
    if not args:
        return None
    try:
        return int(args[0])
    except ValueError:
        return None


def format_user_display(user: BotUser) -> str:
    if user.username:
        return f"@{user.username}"
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return full_name or "no profile name"


def user_now(user: BotUser, settings: Settings) -> datetime:
    """The current time in the user's timezone: "today" and the date buttons are computed from it."""
    return datetime.now(tz=user_timezone(user, settings))


async def edit_message(query: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None) -> None:
    """Edit the tapped message in place; an unchanged message is not an error."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def send_menu(message: Message, context: ContextTypes.DEFAULT_TYPE, user: BotUser) -> None:
    trackers = await _active_trackers(context)
    now = user_now(user, context.application.bot_data["settings"])
    await message.reply_html(
        tracker_menu_text(trackers), reply_markup=tracker_menu_keyboard(trackers, (now.year, now.month))
    )


async def show_menu(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, user: BotUser) -> None:
    trackers = await _active_trackers(context)
    now = user_now(user, context.application.bot_data["settings"])
    await edit_message(query, tracker_menu_text(trackers), tracker_menu_keyboard(trackers, (now.year, now.month)))


async def _active_trackers(context: ContextTypes.DEFAULT_TYPE) -> list[Tracker]:
    tracker_service: TrackerService = context.application.bot_data["tracker_service"]
    return await tracker_service.list_active()
