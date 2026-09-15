"""Tracker registry operations (requirements §4.3). Sheets calls go through the injected SheetsClient."""

from __future__ import annotations

import logging
import re

from tally.persistence import Tracker
from tally.repositories import TrackerRepository
from tally.sheets import HEADER, SheetsClient, SheetsError, header_matches

logger = logging.getLogger(__name__)

KEY_PATTERN = re.compile(r"^[a-z0-9_]{1,16}$")
MAX_LABEL_LENGTH = 32


class TrackerError(ValueError):
    """A registry operation was refused; the message is meant for the user."""


def validate_key(key: str) -> str:
    candidate = key.strip()
    if not KEY_PATTERN.match(candidate):
        msg = "Key must be 1-16 characters of a-z, 0-9 or _"
        raise TrackerError(msg)
    return candidate


def validate_label(label: str) -> str:
    candidate = " ".join(label.split())
    if not candidate:
        msg = "Label must not be empty"
        raise TrackerError(msg)
    if len(candidate) > MAX_LABEL_LENGTH:
        msg = f"Label must be at most {MAX_LABEL_LENGTH} characters"
        raise TrackerError(msg)
    return candidate


def default_label(key: str) -> str:
    return key.upper()


class TrackerService:
    def __init__(self, tracker_repo: TrackerRepository, sheets: SheetsClient) -> None:
        self._tracker_repo = tracker_repo
        self._sheets = sheets

    async def list_all(self) -> list[Tracker]:
        return await self._tracker_repo.list_all()

    async def list_active(self) -> list[Tracker]:
        return [tracker for tracker in await self._tracker_repo.list_all() if tracker.is_active]

    async def get(self, key: str) -> Tracker | None:
        return await self._tracker_repo.get(key)

    async def get_active(self, key: str) -> Tracker | None:
        tracker = await self._tracker_repo.get(key)
        return tracker if tracker is not None and tracker.is_active else None

    async def create(self, key: str, label: str | None = None) -> Tracker:
        """/new: a worksheet named <key> with the contract header, then the registry row. No side effects on refusal."""
        key = validate_key(key)
        label = validate_label(label) if label else default_label(key)
        await self._require_free_key(key)
        if await self._sheets.read_header(key) is not None:
            msg = f"A worksheet named {key!r} already exists; use /attach {key} {key}"
            raise TrackerError(msg)
        await self._sheets.create_worksheet(key, HEADER)
        return await self._tracker_repo.create(key=key, label=label, worksheet=key)

    async def attach(self, key: str, worksheet: str, label: str | None = None) -> Tracker:
        """/attach: register an existing worksheet whose header is exactly the contract."""
        key = validate_key(key)
        worksheet = worksheet.strip()
        if not worksheet:
            msg = "Worksheet name must not be empty"
            raise TrackerError(msg)
        label = validate_label(label) if label else default_label(key)
        await self._require_free_key(key)
        header = await self._sheets.read_header(worksheet)
        if header is None:
            msg = f"Worksheet {worksheet!r} not found"
            raise TrackerError(msg)
        if not header_matches(header):
            msg = f"Worksheet {worksheet!r} header is {' | '.join(header) or '(empty)'}; expected {' | '.join(HEADER)}"
            raise TrackerError(msg)
        return await self._tracker_repo.create(key=key, label=label, worksheet=worksheet)

    async def rename(self, key: str, label: str) -> Tracker:
        key = validate_key(key)
        label = validate_label(label)
        return self._require_found(await self._tracker_repo.set_label(key, label), key)

    async def archive(self, key: str) -> Tracker:
        return await self._set_archived(key, True)

    async def unarchive(self, key: str) -> Tracker:
        return await self._set_archived(key, False)

    async def detach(self, key: str) -> Tracker:
        """Registry only: the worksheet is never touched (requirements §8)."""
        key = validate_key(key)
        return self._require_found(await self._tracker_repo.delete(key), key)

    async def check_worksheet(self, tracker: Tracker) -> str | None:
        """None when the tracker's worksheet exists with the contract header, else a short problem description."""
        try:
            header = await self._sheets.read_header(tracker.worksheet)
        except SheetsError as exc:
            logger.warning("tracker %r: cannot read worksheet %r: %s", tracker.key, tracker.worksheet, exc)
            return str(exc)
        if header is None:
            return f"worksheet {tracker.worksheet!r} not found"
        if not header_matches(header):
            return f"worksheet {tracker.worksheet!r} header is {header!r}, expected {list(HEADER)!r}"
        return None

    async def _set_archived(self, key: str, archived: bool) -> Tracker:
        key = validate_key(key)
        return self._require_found(await self._tracker_repo.set_archived(key, archived), key)

    async def _require_free_key(self, key: str) -> None:
        if await self._tracker_repo.get(key) is not None:
            msg = f"Tracker {key!r} already exists"
            raise TrackerError(msg)

    @staticmethod
    def _require_found(tracker: Tracker | None, key: str) -> Tracker:
        if tracker is None:
            msg = f"No tracker {key!r}"
            raise TrackerError(msg)
        return tracker
