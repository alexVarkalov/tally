from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application

from tally.config import Settings, load_dotenv_if_present
from tally.db import Database
from tally.handlers import register_handlers
from tally.repositories import TrackerRepository, UserRepository
from tally.services import RecordService, StatsService, TrackerService, UserService
from tally.sheets import SheetsClient, SheetsError

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    await db.init()

    settings: Settings = application.bot_data["settings"]
    application.bot_data["user_service"] = UserService(UserRepository(db))

    sheets = SheetsClient(
        service_account_file=settings.google_service_account_file,
        spreadsheet_id=settings.google_spreadsheet_id,
    )
    tracker_service = TrackerService(TrackerRepository(db), sheets)
    application.bot_data["tracker_service"] = tracker_service
    application.bot_data["record_service"] = RecordService(sheets)
    application.bot_data["stats_service"] = StatsService(sheets)
    try:
        await sheets.ensure_ready()
    except SheetsError:
        # Keep running: commands still work and every failed append is reported to the user and the log.
        logger.exception("Google Sheets is not reachable at startup; check GOOGLE_* settings and sharing")
        return
    await _check_trackers(tracker_service)


async def _check_trackers(tracker_service: TrackerService) -> None:
    """Log every registered tracker whose worksheet is missing or has a foreign header. Never fatal."""
    trackers = await tracker_service.list_all()
    for tracker in trackers:
        problem = await tracker_service.check_worksheet(tracker)
        if problem is None:
            logger.info("tracker %r → worksheet %r ok", tracker.key, tracker.worksheet)
        else:
            logger.warning("tracker %r unavailable: %s", tracker.key, problem)
    logger.info("%d tracker(s) registered", len(trackers))


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
