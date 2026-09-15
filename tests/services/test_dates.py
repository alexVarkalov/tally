from __future__ import annotations

from datetime import date

from tally.services.dates import (
    format_day,
    format_day_long,
    month_key,
    month_short_title,
    month_title,
    next_month,
    parse_month_key,
    prev_month,
)


def test_day_formats_are_english_regardless_of_locale() -> None:
    assert format_day(date(2026, 9, 15)) == "Tue 15"
    assert format_day(date(2026, 9, 5)) == "Sat 5"
    assert format_day_long(date(2026, 9, 15)) == "Tue 15 Sep 2026"


def test_month_titles_and_keys() -> None:
    assert month_title(2026, 9) == "September 2026"
    assert month_short_title(2026, 9) == "Sep 2026"
    assert month_key(2026, 9) == "2026-09"
    assert parse_month_key("2026-09") == (2026, 9)
    assert parse_month_key("2026-13") is None
    assert parse_month_key("nope") is None
    assert parse_month_key("2026-09-15") is None


def test_month_navigation_wraps_years() -> None:
    assert prev_month(2026, 1) == (2025, 12)
    assert prev_month(2026, 9) == (2026, 8)
    assert next_month(2026, 12) == (2027, 1)
    assert next_month(2026, 9) == (2026, 10)
