from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from tally.services.records import RecordRow, RecordService, author_label, build_row, date_choices
from tally.sheets import SheetsError
from tests.helpers import make_tracker, make_user

NOW_LOCAL = datetime(2026, 9, 15, 14, 39, 1, 123456, tzinfo=ZoneInfo("Europe/Warsaw"))


def test_author_label_prefers_username_then_name_then_id() -> None:
    assert author_label(make_user(username="alex")) == "alex"
    assert author_label(make_user(username=None, first_name="A", last_name="B")) == "A B"
    assert author_label(make_user(telegram_id=7, username=None, first_name=None, last_name=None)) == "7"


def test_date_choices_oldest_first_today_last() -> None:
    today = date(2026, 3, 1)
    assert date_choices(today, 3) == [date(2026, 2, 27), date(2026, 2, 28), today]
    assert date_choices(today, 1) == [today]


def test_build_row_matches_the_spreadsheet_contract() -> None:
    row = build_row(make_tracker(worksheet="my-counter"), date(2026, 9, 5), NOW_LOCAL, make_user(username="alex"))

    assert row == RecordRow(
        worksheet="my-counter",
        values=("2026", "9", "5", "2026-09-15 14:39:01", "alex", ""),
    )


def test_build_row_uses_the_tapped_day_not_the_write_time() -> None:
    row = build_row(make_tracker(), date(2025, 12, 31), NOW_LOCAL, make_user())

    assert row.values[:3] == ("2025", "12", "31")
    assert row.values[3].startswith("2026-09-15")


@pytest.mark.asyncio
async def test_record_service_appends_the_row() -> None:
    sheets = AsyncMock()
    service = RecordService(sheets)

    row = await service.record(make_tracker(worksheet="gym"), date(2026, 9, 15), NOW_LOCAL, make_user(username="alex"))

    sheets.append_row.assert_awaited_once_with("gym", ("2026", "9", "15", "2026-09-15 14:39:01", "alex", ""))
    assert row.worksheet == "gym"


@pytest.mark.asyncio
async def test_record_service_propagates_sheets_error() -> None:
    sheets = AsyncMock()
    sheets.append_row.side_effect = SheetsError("down")

    with pytest.raises(SheetsError):
        await RecordService(sheets).record(make_tracker(), date(2026, 9, 15), NOW_LOCAL, make_user())
