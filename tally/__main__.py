from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application

from tally.config import Settings, load_dotenv_if_present
from tally.db import Database
from tally.handlers import register_handlers
from tally.repositories import UserRepository
from tally.services import UserService

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    await db.init()

    application.bot_data["user_service"] = UserService(UserRepository(db))


def main() -> None:
    load_dotenv_if_present()
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # The old bot logged every Telegram request, token included, at INFO (requirements §9).
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc

    application = Application.builder().token(settings.bot_token).post_init(_post_init).build()
    application.bot_data["settings"] = settings
    application.bot_data["db"] = Database(settings.database_url)

    register_handlers(application)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
