from __future__ import annotations

from datetime import UTC, datetime

from tally.config import Settings
from tally.persistence import BotUser, Tracker


def make_user(**overrides: object) -> BotUser:
    now = datetime.now(tz=UTC)
    defaults: dict[str, object] = {
        "telegram_id": 123,
        "username": "tester",
        "first_name": "Test",
        "last_name": "User",
        "language_code": "en",
        "preferred_locale": None,
        "timezone": "UTC",
        "is_allowed": True,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }
    defaults.update(overrides)
    return BotUser(**defaults)


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "bot_token": "token",
        "database_url": "postgresql+psycopg://tally:tally@localhost:5432/tally",
        "admin_user_ids": frozenset({999}),
        "google_service_account_file": "data/service-account.json",
        "google_spreadsheet_id": "sheet-id",
        "default_timezone": "Europe/Warsaw",
        "day_choices": 3,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_tracker(**overrides: object) -> Tracker:
    defaults: dict[str, object] = {
        "id": 1,
        "key": "my",
        "label": "MY",
        "worksheet": "my-counter",
        "position": 1,
        "archived_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Tracker(**defaults)
