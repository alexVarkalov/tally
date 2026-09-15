from __future__ import annotations

import os
from dataclasses import dataclass

MAX_DAY_CHOICES = 7


def load_dotenv_if_present() -> None:
    """Minimal .env loader to avoid an extra dependency; ignores parse errors."""
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        return


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    admin_user_ids: frozenset[int]
    google_service_account_file: str
    google_spreadsheet_id: str
    default_timezone: str = "Europe/Warsaw"
    day_choices: int = 3

    @classmethod
    def from_env(cls) -> Settings:
        token = os.environ.get("BOT_TOKEN", "").strip()
        if not token:
            msg = "BOT_TOKEN is required"
            raise ValueError(msg)

        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://tally:tally@localhost:5432/tally",
        ).strip()
        if not database_url:
            msg = "DATABASE_URL is required"
            raise ValueError(msg)

        admin_user_ids = _parse_user_ids(os.environ.get("ADMIN_USER_IDS", ""))

        service_account_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        if not service_account_file:
            msg = "GOOGLE_SERVICE_ACCOUNT_FILE is required (path to the service-account JSON key)"
            raise ValueError(msg)
        if not os.path.isfile(service_account_file):
            msg = f"GOOGLE_SERVICE_ACCOUNT_FILE does not exist: {service_account_file}"
            raise ValueError(msg)

        spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID", "").strip()
        if not spreadsheet_id:
            msg = "GOOGLE_SPREADSHEET_ID is required (the /d/<id>/ part of the sheet URL)"
            raise ValueError(msg)

        default_timezone = os.environ.get("DEFAULT_TIMEZONE", "").strip() or "Europe/Warsaw"
        day_choices = min(MAX_DAY_CHOICES, _int_env("DAY_CHOICES", default=3, minimum=1))

        return cls(
            bot_token=token,
            database_url=database_url,
            admin_user_ids=admin_user_ids,
            google_service_account_file=service_account_file,
            google_spreadsheet_id=spreadsheet_id,
            default_timezone=default_timezone,
            day_choices=day_choices,
        )


def _int_env(name: str, *, default: int, minimum: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _parse_user_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        value = part.strip()
        if not value:
            continue
        try:
            ids.add(int(value))
        except ValueError:
            continue
    return frozenset(ids)
