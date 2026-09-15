from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tally.repositories.trackers import TrackerRepository


@pytest.mark.asyncio
async def test_tracker_repository_methods_delegate_to_db() -> None:
    db = AsyncMock()
    repo = TrackerRepository(db)

    await repo.list_all()
    await repo.get("my")
    await repo.create(key="my", label="MY", worksheet="my-counter")
    await repo.set_label("my", "Mine")
    await repo.set_archived("my", True)
    await repo.delete("my")

    db.list_trackers.assert_awaited_once_with()
    db.get_tracker.assert_awaited_once_with("my")
    db.create_tracker.assert_awaited_once_with(key="my", label="MY", worksheet="my-counter")
    db.set_tracker_label.assert_awaited_once_with("my", "Mine")
    db.set_tracker_archived.assert_awaited_once_with("my", True)
    db.delete_tracker.assert_awaited_once_with("my")
