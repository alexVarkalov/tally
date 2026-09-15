"""Month statistics (requirements §4.4). Everything but fetch_days is pure and reads the counted day from the
Year/Month/Day columns only: rows are edited by hand in the sheet and are not in date order."""

from __future__ import annotations

import html
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from tally.i18n import t
from tally.persistence import Tracker
from tally.services.dates import format_day, format_day_long, month_name, month_title
from tally.sheets import SheetsClient


@dataclass(frozen=True)
class MonthSummary:
    year: int
    month: int
    total: int
    per_day: tuple[tuple[date, int], ...]  # calendar order, only days with at least one row

    def count_on(self, day: date) -> int:
        return next((count for candidate, count in self.per_day if candidate == day), 0)


@dataclass(frozen=True)
class TrackerDays:
    label: str
    days: tuple[date, ...] | None  # None: the worksheet could not be read


def parse_rows(records: Iterable[Mapping[str, object]]) -> list[date]:
    """One date per row from Year/Month/Day; rows where they are not a valid date are skipped."""
    days: list[date] = []
    for record in records:
        try:
            day = date(int(record["Year"]), int(record["Month"]), int(record["Day"]))
        except KeyError, TypeError, ValueError:
            continue
        days.append(day)
    return days


def month_summary(days: Iterable[date], year: int, month: int) -> MonthSummary:
    counts = Counter(day for day in days if day.year == year and day.month == month)
    per_day = tuple(sorted(counts.items()))
    return MonthSummary(year=year, month=month, total=sum(counts.values()), per_day=per_day)


def year_total(days: Iterable[date], year: int) -> int:
    return sum(1 for day in days if day.year == year)


def render_month(year: int, month: int, items: Sequence[TrackerDays]) -> str:
    """HTML message for one month across trackers, in the given order; labels are user input and get escaped."""
    lines = [t("stats_title", month=html.escape(month_title(year, month)))]
    if not items:
        lines.extend(["", t("stats_empty")])
        return "\n".join(lines)

    year_parts: list[str] = []
    for item in items:
        label = html.escape(item.label)
        lines.append("")
        if item.days is None:
            lines.append(t("stats_tracker_unavailable", label=label))
            year_parts.append(t("stats_year_part_unavailable", label=label))
            continue
        summary = month_summary(item.days, year, month)
        lines.append(t("stats_tracker_line", label=label, total=summary.total))
        lines.extend(t("stats_day_line", day=format_day(day), count=count) for day, count in summary.per_day)
        year_parts.append(t("stats_year_part", label=label, total=year_total(item.days, year)))

    lines.extend(["", t("stats_year_line", year=year, parts=" · ".join(year_parts))])
    return "\n".join(lines)


def render_confirmation(label: str, day: date, summary: MonthSummary | None) -> str:
    """`✅ <label> · Mon 15 Sep 2026 recorded. September: 4 (that day: 2)`; the numbers are optional."""
    text = t("recorded", label=html.escape(label), day=format_day_long(day))
    if summary is None:
        return text
    return text + t("recorded_counts", month=month_name(day.month), total=summary.total, on_day=summary.count_on(day))


class StatsService:
    def __init__(self, sheets: SheetsClient) -> None:
        self._sheets = sheets

    async def fetch_days(self, tracker: Tracker) -> list[date]:
        """Every counted day of the tracker; raises SheetsError when the worksheet is missing or foreign."""
        return parse_rows(await self._sheets.read_rows(tracker.worksheet))
