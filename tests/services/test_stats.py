from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from tally.services.stats import (
    MonthSummary,
    StatsService,
    TrackerDays,
    month_summary,
    parse_rows,
    render_confirmation,
    render_month,
    year_total,
)
from tally.sheets import SheetsError
from tests.helpers import make_tracker

DAYS = [
    date(2026, 9, 15),
    date(2026, 9, 13),
    date(2026, 9, 15),
    date(2026, 9, 15),
    date(2026, 8, 30),
    date(2025, 9, 15),
]


def test_parse_rows_accepts_ints_and_strings_and_skips_junk() -> None:
    records = [
        {"Year": 2026, "Month": 9, "Day": 15, "Created at": "x", "Username": "u", "Comment": ""},
        {"Year": "2026", "Month": "9", "Day": "13"},
        {"Year": "", "Month": "", "Day": ""},
        {"Year": "2026", "Month": "2", "Day": "30"},
        {"Year": "abc", "Month": "1", "Day": "1"},
        {"Month": "1", "Day": "1"},
        {"Year": None, "Month": "1", "Day": "1"},
    ]

    assert parse_rows(records) == [date(2026, 9, 15), date(2026, 9, 13)]


def test_month_summary_counts_per_day_in_calendar_order() -> None:
    summary = month_summary(DAYS, 2026, 9)

    assert summary == MonthSummary(
        year=2026, month=9, total=4, per_day=((date(2026, 9, 13), 1), (date(2026, 9, 15), 3))
    )
    assert summary.count_on(date(2026, 9, 15)) == 3
    assert summary.count_on(date(2026, 9, 1)) == 0
    assert month_summary(DAYS, 2026, 7).total == 0


def test_year_total() -> None:
    assert year_total(DAYS, 2026) == 5
    assert year_total(DAYS, 2024) == 0


def test_render_month_matches_the_requirements_example() -> None:
    text = render_month(
        2026,
        9,
        [
            TrackerDays("MY", tuple(DAYS)),
            TrackerDays("OUR", (date(2026, 1, 1),) * 7),
        ],
    )

    assert text == (
        "📊 <b>September 2026</b>\n"
        "\n"
        "<b>MY</b> — 4\n"
        "  Sun 13 · 1\n"
        "  Tue 15 · 3\n"
        "\n"
        "<b>OUR</b> — 0\n"
        "\n"
        "Year 2026: MY 5 · OUR 7"
    )


def test_render_month_shows_unavailable_trackers_and_escapes_labels() -> None:
    text = render_month(2026, 9, [TrackerDays("<b>Gym</b>", None), TrackerDays("MY", ())])

    assert "<b>&lt;b&gt;Gym&lt;/b&gt;</b> — ⚠ unavailable" in text
    assert "<b>MY</b> — 0" in text
    assert text.endswith("Year 2026: &lt;b&gt;Gym&lt;/b&gt; ⚠ · MY 0")


def test_render_month_without_trackers() -> None:
    text = render_month(2026, 9, [])

    assert "September 2026" in text
    assert "/new" in text


def test_render_confirmation_with_and_without_counts() -> None:
    summary = month_summary(DAYS, 2026, 9)

    assert render_confirmation("MY", date(2026, 9, 15), summary) == (
        "✅ MY · Tue 15 Sep 2026 recorded. September: 4 (that day: 3)"
    )
    assert render_confirmation("<x>", date(2026, 9, 15), None) == "✅ &lt;x&gt; · Tue 15 Sep 2026 recorded."


@pytest.mark.asyncio
async def test_stats_service_fetches_and_parses_rows() -> None:
    sheets = AsyncMock()
    sheets.read_rows.return_value = [{"Year": "2026", "Month": "9", "Day": "15"}, {"Year": "", "Month": "", "Day": ""}]

    days = await StatsService(sheets).fetch_days(make_tracker(worksheet="my-counter"))

    sheets.read_rows.assert_awaited_once_with("my-counter")
    assert days == [date(2026, 9, 15)]


@pytest.mark.asyncio
async def test_stats_service_propagates_sheets_error() -> None:
    sheets = AsyncMock()
    sheets.read_rows.side_effect = SheetsError("gone")

    with pytest.raises(SheetsError):
        await StatsService(sheets).fetch_days(make_tracker())
