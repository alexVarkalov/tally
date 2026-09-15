"""English date formatting without depending on the process locale. Pure."""

from __future__ import annotations

from datetime import date

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def weekday_abbr(day: date) -> str:
    return WEEKDAYS[day.weekday()]


def month_name(month: int) -> str:
    return MONTHS[month - 1]


def month_abbr(month: int) -> str:
    return MONTHS[month - 1][:3]


def format_day(day: date) -> str:
    """`Mon 15`: weekday and day of month, as on the date buttons and in the stats."""
    return f"{weekday_abbr(day)} {day.day}"


def format_day_long(day: date) -> str:
    """`Mon 15 Sep 2026`, as in the record confirmation."""
    return f"{weekday_abbr(day)} {day.day} {month_abbr(day.month)} {day.year}"


def month_title(year: int, month: int) -> str:
    return f"{month_name(month)} {year}"


def month_short_title(year: int, month: int) -> str:
    return f"{month_abbr(month)} {year}"


def month_key(year: int, month: int) -> str:
    """`YYYY-MM`, the stats callback payload."""
    return f"{year:04d}-{month:02d}"


def parse_month_key(value: str) -> tuple[int, int] | None:
    """Inverse of month_key; None for anything that is not a valid `YYYY-MM`."""
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError:
        return None
    return parsed.year, parsed.month


def prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)
