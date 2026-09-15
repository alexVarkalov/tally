from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from tally.persistence.models import TrackerRecord
from tally.persistence.types import Tracker
from tally.persistence.utils import to_tracker, utc_now


class TrackerStore:
    async def list_trackers(self) -> list[Tracker]:
        return await asyncio.to_thread(self._list_trackers_sync)

    def _list_trackers_sync(self) -> list[Tracker]:
        with self._session_factory() as session:
            rows = session.scalars(select(TrackerRecord).order_by(TrackerRecord.position, TrackerRecord.id)).all()
            return [to_tracker(record) for record in rows]

    async def get_tracker(self, key: str) -> Tracker | None:
        return await asyncio.to_thread(self._get_tracker_sync, key)

    def _get_tracker_sync(self, key: str) -> Tracker | None:
        with self._session_factory() as session:
            record = session.scalar(select(TrackerRecord).where(TrackerRecord.key == key))
            return to_tracker(record) if record is not None else None

    async def create_tracker(self, *, key: str, label: str, worksheet: str) -> Tracker:
        return await asyncio.to_thread(self._create_tracker_sync, key, label, worksheet)

    def _create_tracker_sync(self, key: str, label: str, worksheet: str) -> Tracker:
        now = utc_now()
        with self._session_factory() as session:
            last_position = session.scalar(select(func.max(TrackerRecord.position)))
            record = TrackerRecord(
                key=key,
                label=label,
                worksheet=worksheet,
                position=(last_position or 0) + 1,
                archived_at=None,
                created_at=now,
            )
            session.add(record)
            session.commit()
            return to_tracker(record)

    async def set_tracker_label(self, key: str, label: str) -> Tracker | None:
        return await asyncio.to_thread(self._set_tracker_label_sync, key, label)

    def _set_tracker_label_sync(self, key: str, label: str) -> Tracker | None:
        with self._session_factory() as session:
            record = session.scalar(select(TrackerRecord).where(TrackerRecord.key == key))
            if record is None:
                return None
            record.label = label
            session.commit()
            return to_tracker(record)

    async def set_tracker_archived(self, key: str, archived: bool) -> Tracker | None:
        return await asyncio.to_thread(self._set_tracker_archived_sync, key, archived)

    def _set_tracker_archived_sync(self, key: str, archived: bool) -> Tracker | None:
        with self._session_factory() as session:
            record = session.scalar(select(TrackerRecord).where(TrackerRecord.key == key))
            if record is None:
                return None
            record.archived_at = utc_now() if archived else None
            session.commit()
            return to_tracker(record)

    async def delete_tracker(self, key: str) -> Tracker | None:
        return await asyncio.to_thread(self._delete_tracker_sync, key)

    def _delete_tracker_sync(self, key: str) -> Tracker | None:
        with self._session_factory() as session:
            record = session.scalar(select(TrackerRecord).where(TrackerRecord.key == key))
            if record is None:
                return None
            tracker = to_tracker(record)
            session.delete(record)
            session.commit()
            return tracker
