from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tally.__main__ import _post_init
from tally.services import RecordService, StatsService, TrackerService, UserService
from tally.sheets import HEADER
from tests.helpers import make_settings, make_tracker


@pytest.mark.asyncio
async def test_post_init_wires_services_and_survives_unreachable_sheets(caplog: pytest.LogCaptureFixture) -> None:
    db = AsyncMock()
    db.list_trackers.return_value = [make_tracker()]
    application = SimpleNamespace(bot_data={"settings": make_settings(), "db": db})

    with caplog.at_level("WARNING"):
        await _post_init(application)

    db.init.assert_awaited_once()
    assert isinstance(application.bot_data["user_service"], UserService)
    assert isinstance(application.bot_data["tracker_service"], TrackerService)
    assert isinstance(application.bot_data["record_service"], RecordService)
    assert isinstance(application.bot_data["stats_service"], StatsService)
    assert "not reachable at startup" in caplog.text


@pytest.mark.asyncio
async def test_post_init_checks_every_tracker_worksheet(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from tally import __main__ as main_module

    ensure_ready = AsyncMock()
    read_header = AsyncMock(side_effect=[list(HEADER), None])
    monkeypatch.setattr(main_module.SheetsClient, "ensure_ready", ensure_ready)
    monkeypatch.setattr(main_module.SheetsClient, "read_header", read_header)
    db = AsyncMock()
    db.list_trackers.return_value = [make_tracker(key="my"), make_tracker(key="gone", worksheet="gone", position=2)]
    application = SimpleNamespace(bot_data={"settings": make_settings(), "db": db})

    with caplog.at_level("INFO"):
        await _post_init(application)

    ensure_ready.assert_awaited_once()
    assert "tracker 'my' → worksheet 'my-counter' ok" in caplog.text
    assert "tracker 'gone' unavailable: worksheet 'gone' not found" in caplog.text
    assert "2 tracker(s) registered" in caplog.text
