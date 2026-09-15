"""Google Sheets access via a service account (gspread). The only module that talks to Google.

Sync gspread calls run in a worker thread behind a lock. The spreadsheet handle and one handle per
worksheet are cached after the first successful open and dropped on any error so the next call
re-authenticates. The worksheet name is passed per call: one worksheet per tracker (requirements §3).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Sequence

import gspread
from gspread.exceptions import WorksheetNotFound

logger = logging.getLogger(__name__)

HEADER: tuple[str, ...] = ("Year", "Month", "Day", "Created at", "Username", "Comment")

# Rows go in with USER_ENTERED so Year/Month/Day become numbers and "Created at" a date cell, like the
# existing rows. A cell starting with one of these would then be parsed as a formula; a leading apostrophe
# makes Sheets store it as literal text, exactly as when typed in the UI. The apostrophe itself is not stored.
_FORMULA_TRIGGERS = ("=", "+", "-", "@")

DEFAULT_TIMEOUT_SECONDS = 20.0


def escape_cell(value: str) -> str:
    return f"'{value}" if value.startswith(_FORMULA_TRIGGERS) else value


def header_matches(header: Sequence[str], expected: Sequence[str] = HEADER) -> bool:
    """True when row 1 is exactly the contract header (trailing empty cells ignored)."""
    cells = [cell.strip() for cell in header]
    while cells and not cells[-1]:
        cells.pop()
    return tuple(cells) == tuple(expected)


class SheetsError(Exception):
    """Google Sheets could not be reached or rejected the request."""


class SheetsClient:
    def __init__(
        self, *, service_account_file: str, spreadsheet_id: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._service_account_file = service_account_file
        self._spreadsheet_id = spreadsheet_id
        self._timeout = timeout
        self._spreadsheet: gspread.Spreadsheet | None = None
        self._worksheets: dict[str, gspread.Worksheet] = {}
        self._lock = threading.Lock()

    async def ensure_ready(self) -> None:
        """Open the spreadsheet once so misconfiguration (key, ID, sharing) shows up at startup."""
        await asyncio.to_thread(self._run, self._open_spreadsheet_sync)

    async def append_row(self, worksheet: str, values: Sequence[str]) -> None:
        escaped = [escape_cell(value) for value in values]
        await asyncio.to_thread(
            self._run,
            lambda: self._open_worksheet_sync(worksheet).append_row(escaped, value_input_option="USER_ENTERED"),
        )

    async def read_header(self, worksheet: str) -> list[str] | None:
        """Row 1 of the worksheet, or None when no worksheet of that name exists. Never served from the cache."""
        return await asyncio.to_thread(self._run, lambda: self._read_header_sync(worksheet))

    async def read_rows(self, worksheet: str) -> list[dict[str, str]]:
        """Every data row as a dict keyed by the contract header; raises SheetsError when the header differs."""
        return await asyncio.to_thread(self._run, lambda: self._read_rows_sync(worksheet))

    async def create_worksheet(self, name: str, header: Sequence[str] = HEADER) -> None:
        """Add a worksheet with the header in row 1. The only structural write the bot ever makes."""
        await asyncio.to_thread(self._run, lambda: self._create_worksheet_sync(name, list(header)))

    def _run[T](self, call: Callable[[], T]) -> T:
        with self._lock:
            try:
                return call()
            except Exception as exc:
                self._spreadsheet = None
                self._worksheets.clear()
                msg = f"{type(exc).__name__}: {exc}"
                raise SheetsError(msg) from exc

    def _open_spreadsheet_sync(self) -> gspread.Spreadsheet:
        if self._spreadsheet is not None:
            return self._spreadsheet
        client = gspread.service_account(filename=self._service_account_file)
        client.set_timeout(self._timeout)
        self._spreadsheet = client.open_by_key(self._spreadsheet_id)
        return self._spreadsheet

    def _open_worksheet_sync(self, name: str) -> gspread.Worksheet:
        cached = self._worksheets.get(name)
        if cached is not None:
            return cached
        worksheet = self._open_spreadsheet_sync().worksheet(name)
        self._worksheets[name] = worksheet
        return worksheet

    def _read_header_sync(self, name: str) -> list[str] | None:
        try:
            worksheet = self._open_spreadsheet_sync().worksheet(name)
        except WorksheetNotFound:
            return None
        return [str(cell) for cell in worksheet.row_values(1)]

    def _read_rows_sync(self, name: str) -> list[dict[str, str]]:
        values = self._open_worksheet_sync(name).get_all_values()
        header = [str(cell) for cell in values[0]] if values else []
        if not header_matches(header):
            msg = f"worksheet {name!r} header is {header!r}, expected {list(HEADER)!r}"
            raise ValueError(msg)
        width = len(HEADER)
        rows = []
        for row in values[1:]:
            cells = [str(cell) for cell in row[:width]] + [""] * (width - len(row))
            rows.append(dict(zip(HEADER, cells, strict=True)))
        return rows

    def _create_worksheet_sync(self, name: str, header: list[str]) -> None:
        spreadsheet = self._open_spreadsheet_sync()
        logger.info("creating worksheet %r", name)
        worksheet = spreadsheet.add_worksheet(title=name, rows=1, cols=len(header))
        worksheet.append_row(header, value_input_option="RAW")
        self._worksheets[name] = worksheet
