from __future__ import annotations

from tally.db import Database
from tally.persistence import Tracker


class TrackerRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_all(self) -> list[Tracker]:
        return await self._db.list_trackers()

    async def get(self, key: str) -> Tracker | None:
        return await self._db.get_tracker(key)

    async def create(self, *, key: str, label: str, worksheet: str) -> Tracker:
        return await self._db.create_tracker(key=key, label=label, worksheet=worksheet)

    async def set_label(self, key: str, label: str) -> Tracker | None:
        return await self._db.set_tracker_label(key, label)

    async def set_archived(self, key: str, archived: bool) -> Tracker | None:
        return await self._db.set_tracker_archived(key, archived)

    async def delete(self, key: str) -> Tracker | None:
        return await self._db.delete_tracker(key)
