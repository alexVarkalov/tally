from __future__ import annotations

import re
from pathlib import Path

import pytest

from tally.config import Settings, _int_env, _parse_user_ids, load_dotenv_if_present


def test_settings_from_env_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", " token ")
    monkeypatch.setenv("ADMIN_USER_IDS", "1, 2, bad")
    monkeypatch.setenv("DEFAULT_TIMEZONE", " Europe/Moscow ")
    monkeypatch.setenv("DAY_CHOICES", "5")

    settings = Settings.from_env()

    assert settings.bot_token == "token"
    assert settings.admin_user_ids == frozenset({1, 2})
    assert settings.database_url.endswith("/tally")
    assert settings.google_spreadsheet_id == "sheet-id"
    assert settings.default_timezone == "Europe/Moscow"
    assert settings.day_choices == 5
    assert Path(settings.google_service_account_file).is_file()


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.delenv("DEFAULT_TIMEZONE", raising=False)
    monkeypatch.delenv("DAY_CHOICES", raising=False)

    settings = Settings.from_env()

    assert settings.default_timezone == "Europe/Warsaw"
    assert settings.day_choices == 3


@pytest.mark.parametrize(("raw", "expected"), [("0", 1), ("12", 7), ("bad", 3), ("", 3)])
def test_settings_day_choices_is_clamped(monkeypatch: pytest.MonkeyPatch, raw: str, expected: int) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("DAY_CHOICES", raw)

    assert Settings.from_env().day_choices == expected


def test_settings_missing_required_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    with pytest.raises(ValueError, match="BOT_TOKEN is required"):
        Settings.from_env()


def test_settings_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("DATABASE_URL", "   ")

    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        Settings.from_env()


def test_settings_missing_service_account_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)

    with pytest.raises(ValueError, match="GOOGLE_SERVICE_ACCOUNT_FILE is required"):
        Settings.from_env()


def test_settings_service_account_file_must_exist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(tmp_path / "missing.json"))

    with pytest.raises(ValueError, match="does not exist"):
        Settings.from_env()


def test_settings_missing_spreadsheet_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "")

    with pytest.raises(ValueError, match="GOOGLE_SPREADSHEET_ID is required"):
        Settings.from_env()


def test_parse_user_ids_helper() -> None:
    assert _parse_user_ids("1;2,abc, 3") == frozenset({1, 2, 3})
    assert _parse_user_ids("") == frozenset()


def test_int_env_clamps_and_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOME_INT", "3")
    assert _int_env("SOME_INT", default=10, minimum=5) == 5
    monkeypatch.setenv("SOME_INT", "bad")
    assert _int_env("SOME_INT", default=10, minimum=5) == 10


def test_load_dotenv_does_not_override_real_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text('# comment\nFROM_FILE="a"\nBOT_TOKEN=from-file\nbroken line\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", "real")
    monkeypatch.delenv("FROM_FILE", raising=False)

    load_dotenv_if_present()

    import os

    assert os.environ["FROM_FILE"] == "a"
    assert os.environ["BOT_TOKEN"] == "real"


def test_env_example_lists_every_setting_read_by_from_env() -> None:
    example = Path(__file__).resolve().parents[1] / ".env.example"
    keys = {line.split("=", 1)[0] for line in example.read_text(encoding="utf-8").splitlines() if "=" in line}
    source = (Path(__file__).resolve().parents[1] / "tally" / "config.py").read_text(encoding="utf-8")

    read_keys = set(re.findall(r'(?:os\.environ\.get|_int_env)\(\s*"([A-Z_]+)"', source))
    assert read_keys == keys
