"""Turning a tap into a spreadsheet row (requirements §3, §4.2). The row builder and date choices are pure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from tally.persistence import BotUser, Tracker
from tally.sheets import SheetsClient


@dataclass(frozen=True)
class RecordRow:
    worksheet: str
    values: tuple[str, ...]


def author_label(user: BotUser) -> str:
    if user.username:
        return user.username
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return full_name or str(user.telegram_id)


def date_choices(today: date, n: int) -> list[date]:
    """The last n days, oldest first, today last."""
    return [today - timedelta(days=offset) for offset in range(n - 1, -1, -1)]


def build_row(tracker: Tracker, day: date, now_local: datetime, user: BotUser) -> RecordRow:
    """Year | Month | Day as plain ints, Created at without microseconds, Comment always empty."""
    return RecordRow(
        worksheet=tracker.worksheet,
        values=(
            str(day.year),
            str(day.month),
            str(day.day),
            now_local.strftime("%Y-%m-%d %H:%M:%S"),
            author_label(user),
            "",
        ),
    )


class RecordService:
    def __init__(self, sheets: SheetsClient) -> None:
        self._sheets = sheets

    async def record(self, tracker: Tracker, day: date, now_local: datetime, user: BotUser) -> RecordRow:
        """Append one row; raises SheetsError when Google is unreachable or the worksheet is gone."""
        row = build_row(tracker, day, now_local, user)
        await self._sheets.append_row(row.worksheet, row.values)
        return row
