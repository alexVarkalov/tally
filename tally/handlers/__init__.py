from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from tally.handlers.callbacks import on_menu, on_record, on_unknown
from tally.handlers.commands import (
    cmd_allow_user,
    cmd_block_user,
    cmd_help,
    cmd_menu,
    cmd_start,
    cmd_timezone,
    cmd_users,
)
from tally.handlers.errors import on_error
from tally.handlers.stats import cmd_stats, on_stats
from tally.handlers.trackers import (
    cmd_archive,
    cmd_attach,
    cmd_detach,
    cmd_new,
    cmd_rename,
    cmd_trackers,
    cmd_unarchive,
)

__all__ = ["register_handlers"]


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("menu", cmd_menu))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("trackers", cmd_trackers))
    application.add_handler(CommandHandler("new", cmd_new))
    application.add_handler(CommandHandler("attach", cmd_attach))
    application.add_handler(CommandHandler("rename", cmd_rename))
    application.add_handler(CommandHandler("archive", cmd_archive))
    application.add_handler(CommandHandler("unarchive", cmd_unarchive))
    application.add_handler(CommandHandler("detach", cmd_detach))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("timezone", cmd_timezone))
    application.add_handler(CommandHandler("tz", cmd_timezone))
    application.add_handler(CommandHandler("users", cmd_users))
    application.add_handler(CommandHandler("allow_user", cmd_allow_user))
    application.add_handler(CommandHandler("block_user", cmd_block_user))
    application.add_handler(CallbackQueryHandler(on_record, pattern=r"^rec:"))
    application.add_handler(CallbackQueryHandler(on_stats, pattern=r"^stats:"))
    application.add_handler(CallbackQueryHandler(on_menu, pattern=r"^menu:"))
    application.add_handler(CallbackQueryHandler(on_unknown))  # last: everything the prefixes above did not claim
    application.add_error_handler(on_error)
