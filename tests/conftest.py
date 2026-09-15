from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _google_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """GOOGLE_* settings are mandatory for Settings.from_env(); tests that check their absence delenv explicitly."""
    key_file = tmp_path / "service-account.json"
    key_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(key_file))
    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "sheet-id")
