from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tally.persistence.models import TrackerRecord
from tally.persistence.trackers import TrackerStore
from tests.persistence.fakes import FakeSession, FakeSessionFactory

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


class TrackersDb(TrackerStore):
    def __init__(self, session: FakeSession):
        self._session_factory = FakeSessionFactory(session)


def _record(key: str = "my", position: int = 1, archived_at: datetime | None = None) -> TrackerRecord:
    return TrackerRecord(
        id=position,
        key=key,
        label=key.upper(),
        worksheet=f"{key}-counter",
        position=position,
        archived_at=archived_at,
        created_at=NOW,
    )


def test_list_trackers_sync_maps_records() -> None:
    db = TrackersDb(FakeSession(scalars_results=[[_record("my", 1), _record("our", 2)]]))

    trackers = db._list_trackers_sync()

    assert [t.key for t in trackers] == ["my", "our"]
    assert trackers[0].worksheet == "my-counter"
    assert trackers[0].is_active is True


def test_get_tracker_sync() -> None:
    assert TrackersDb(FakeSession(scalar_results=[None]))._get_tracker_sync("x") is None
    found = TrackersDb(FakeSession(scalar_results=[_record("my")]))._get_tracker_sync("my")
    assert found is not None and found.key == "my"


def test_create_tracker_sync_appends_after_last_position(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(scalar_results=[2])
    monkeypatch.setattr("tally.persistence.trackers.utc_now", lambda: NOW)

    tracker = TrackersDb(session)._create_tracker_sync("gym", "Gym", "gym")

    assert tracker.key == "gym"
    assert tracker.label == "Gym"
    assert tracker.worksheet == "gym"
    assert tracker.position == 3
    assert tracker.archived_at is None
    assert tracker.created_at == NOW
    assert len(session.added) == 1
    assert session.committed == 1


def test_create_tracker_sync_first_tracker_gets_position_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tally.persistence.trackers.utc_now", lambda: NOW)

    assert TrackersDb(FakeSession(scalar_results=[None]))._create_tracker_sync("my", "MY", "my-counter").position == 1


def test_set_tracker_label_sync() -> None:
    session = FakeSession(scalar_results=[_record("my")])

    tracker = TrackersDb(session)._set_tracker_label_sync("my", "Mine")

    assert tracker is not None and tracker.label == "Mine"
    assert session.committed == 1
    assert TrackersDb(FakeSession(scalar_results=[None]))._set_tracker_label_sync("x", "X") is None


def test_set_tracker_archived_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tally.persistence.trackers.utc_now", lambda: NOW)

    archived = TrackersDb(FakeSession(scalar_results=[_record("my")]))._set_tracker_archived_sync("my", True)
    restored = TrackersDb(FakeSession(scalar_results=[_record("my", archived_at=NOW)]))._set_tracker_archived_sync(
        "my", False
    )

    assert archived is not None and archived.archived_at == NOW and archived.is_active is False
    assert restored is not None and restored.archived_at is None
    assert TrackersDb(FakeSession(scalar_results=[None]))._set_tracker_archived_sync("x", True) is None


def test_delete_tracker_sync() -> None:
    session = FakeSession(scalar_results=[_record("my")])

    tracker = TrackersDb(session)._delete_tracker_sync("my")

    assert tracker is not None and tracker.key == "my"
    assert len(session.deleted) == 1
    assert session.committed == 1
    assert TrackersDb(FakeSession(scalar_results=[None]))._delete_tracker_sync("x") is None
