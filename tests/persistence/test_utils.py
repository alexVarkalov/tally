from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from tally.persistence.utils import to_tracker, to_user, utc_now


def test_utc_now_is_aware_utc() -> None:
    assert utc_now().tzinfo is UTC


def test_to_user_maps_every_field_and_coerces_bool() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    record = SimpleNamespace(
        telegram_id=1,
        username="u",
        first_name="f",
        last_name="l",
        language_code="ru",
        preferred_locale="en",
        timezone="Europe/Warsaw",
        is_allowed=1,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )

    user = to_user(record)

    assert user.telegram_id == 1
    assert user.preferred_locale == "en"
    assert user.timezone == "Europe/Warsaw"
    assert user.is_allowed is True
    assert user.last_seen_at == now


def test_to_tracker_maps_every_field() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    record = SimpleNamespace(
        id=3, key="gym", label="🏋️ Gym", worksheet="gym", position=3, archived_at=now, created_at=now
    )

    tracker = to_tracker(record)

    assert tracker.id == 3
    assert tracker.key == "gym"
    assert tracker.label == "🏋️ Gym"
    assert tracker.worksheet == "gym"
    assert tracker.position == 3
    assert tracker.archived_at == now
    assert tracker.is_active is False
