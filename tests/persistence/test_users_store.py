from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tally.persistence.users import UserStore
from tests.persistence.fakes import FakeInsert, FakeSession, FakeSessionFactory


class UsersDb(UserStore):
    def __init__(self, session: FakeSession):
        self._session_factory = FakeSessionFactory(session)


def _fake_user_record(telegram_id: int = 1) -> SimpleNamespace:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return SimpleNamespace(
        telegram_id=telegram_id,
        username="u",
        first_name="f",
        last_name="l",
        language_code="en",
        preferred_locale=None,
        timezone="UTC",
        is_allowed=False,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )


def _patch_select(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tally.persistence.users.select", lambda *_a, **_k: SimpleNamespace(where=lambda *_a2, **_k2: object())
    )


class FakeUserRecord:
    telegram_id = object()

    def __init__(self, **kwargs: object):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_get_user_sync_none() -> None:
    db = UsersDb(FakeSession(scalar_results=[None]))
    assert db._get_user_sync(1) is None


def test_get_user_sync_some(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _fake_user_record(1)
    db = UsersDb(FakeSession(scalar_results=[record]))
    monkeypatch.setattr("tally.persistence.users.to_user", lambda r: r)

    assert db._get_user_sync(1) == record


def test_upsert_user_seen_sync_raises_if_read_back_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    db = UsersDb(FakeSession(scalar_results=[None]))
    monkeypatch.setattr("tally.persistence.users.pg_insert", lambda _model: FakeInsert())
    _patch_select(monkeypatch)
    monkeypatch.setattr("tally.persistence.users.utc_now", lambda: datetime(2026, 1, 1, tzinfo=UTC))

    with pytest.raises(RuntimeError, match="failed to read user after upsert"):
        db._upsert_user_seen_sync(1, "u", "f", "l", "en")


def test_upsert_user_seen_sync_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _fake_user_record(1)
    session = FakeSession(scalar_results=[record])
    db = UsersDb(session)
    monkeypatch.setattr("tally.persistence.users.pg_insert", lambda _model: FakeInsert())
    _patch_select(monkeypatch)
    monkeypatch.setattr("tally.persistence.users.utc_now", lambda: datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr("tally.persistence.users.to_user", lambda r: r)

    out = db._upsert_user_seen_sync(1, "u", "f", "l", "en")

    assert out == record
    assert session.executed
    assert session.committed == 1


def test_set_user_allowed_creates_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(scalar_results=[None])
    db = UsersDb(session)
    monkeypatch.setattr("tally.persistence.users.utc_now", lambda: datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr("tally.persistence.users.UserRecord", FakeUserRecord)
    _patch_select(monkeypatch)
    monkeypatch.setattr("tally.persistence.users.to_user", lambda r: r)

    user = db._set_user_allowed_sync(1, True)

    assert user.is_allowed is True
    assert session.added
    assert session.committed == 1


def test_set_user_allowed_updates_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _fake_user_record(1)
    session = FakeSession(scalar_results=[record])
    db = UsersDb(session)
    monkeypatch.setattr("tally.persistence.users.utc_now", lambda: datetime(2026, 1, 2, tzinfo=UTC))
    monkeypatch.setattr("tally.persistence.users.to_user", lambda r: r)

    user = db._set_user_allowed_sync(1, True)

    assert user.is_allowed is True
    assert user.updated_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert session.committed == 1


@pytest.mark.parametrize(
    ("method", "field", "value"),
    [
        ("_set_user_timezone_sync", "timezone", "Europe/Warsaw"),
    ],
)
def test_setters_create_record_when_missing(
    monkeypatch: pytest.MonkeyPatch, method: str, field: str, value: str
) -> None:
    session = FakeSession(scalar_results=[None])
    db = UsersDb(session)
    monkeypatch.setattr("tally.persistence.users.utc_now", lambda: datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr("tally.persistence.users.UserRecord", FakeUserRecord)
    _patch_select(monkeypatch)
    monkeypatch.setattr("tally.persistence.users.to_user", lambda r: r)

    user = getattr(db, method)(1, value)

    assert getattr(user, field) == value
    assert session.added
    assert session.committed == 1


@pytest.mark.parametrize(
    ("method", "field", "value"),
    [
        ("_set_user_timezone_sync", "timezone", "Europe/Warsaw"),
    ],
)
def test_setters_update_record_when_present(
    monkeypatch: pytest.MonkeyPatch, method: str, field: str, value: str
) -> None:
    record = _fake_user_record(1)
    session = FakeSession(scalar_results=[record])
    db = UsersDb(session)
    monkeypatch.setattr("tally.persistence.users.to_user", lambda r: r)

    user = getattr(db, method)(1, value)

    assert getattr(user, field) == value
    assert not session.added
    assert session.committed == 1


def test_list_users_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    r1, r2 = _fake_user_record(1), _fake_user_record(2)
    db = UsersDb(FakeSession(scalars_results=[[r1, r2]]))
    monkeypatch.setattr(
        "tally.persistence.users.select",
        lambda *_a, **_k: SimpleNamespace(
            order_by=lambda *_a2, **_k2: SimpleNamespace(limit=lambda *_a3, **_k3: object())
        ),
    )
    monkeypatch.setattr("tally.persistence.users.to_user", lambda r: r)

    assert db._list_users_sync(limit=2) == [r1, r2]
