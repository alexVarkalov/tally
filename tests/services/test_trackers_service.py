from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from tally.services.trackers import TrackerError, TrackerService, default_label, validate_key, validate_label
from tally.sheets import HEADER, SheetsError
from tests.helpers import make_tracker


def _service(repo: AsyncMock | None = None, sheets: AsyncMock | None = None) -> TrackerService:
    return TrackerService(repo or AsyncMock(), sheets or AsyncMock())


def test_validate_key() -> None:
    assert validate_key(" my ") == "my"
    assert validate_key("a_1234567890123") == "a_1234567890123"
    for bad in ("", "MY", "my-counter", "a" * 17, "my counter", "ключ"):
        with pytest.raises(TrackerError):
            validate_key(bad)


def test_validate_label_and_default() -> None:
    assert validate_label("  🏋️  Gym ") == "🏋️ Gym"
    assert default_label("gym") == "GYM"
    with pytest.raises(TrackerError, match="empty"):
        validate_label("   ")
    with pytest.raises(TrackerError, match="32"):
        validate_label("x" * 33)


@pytest.mark.asyncio
async def test_list_active_and_get_active_filter_archived() -> None:
    archived = make_tracker(key="our", archived_at=datetime(2026, 1, 1, tzinfo=UTC))
    repo = AsyncMock()
    repo.list_all.return_value = [make_tracker(key="my"), archived]
    repo.get.return_value = archived
    service = _service(repo)

    assert [t.key for t in await service.list_active()] == ["my"]
    assert [t.key for t in await service.list_all()] == ["my", "our"]
    assert await service.get_active("our") is None
    assert await service.get("our") is archived

    repo.get.return_value = None
    assert await service.get_active("nope") is None


@pytest.mark.asyncio
async def test_create_makes_worksheet_then_registers() -> None:
    repo, sheets = AsyncMock(), AsyncMock()
    repo.get.return_value = None
    sheets.read_header.return_value = None
    repo.create.return_value = make_tracker(key="gym", label="🏋️ Gym", worksheet="gym")

    tracker = await _service(repo, sheets).create("gym", "🏋️ Gym")

    assert tracker.key == "gym"
    sheets.create_worksheet.assert_awaited_once_with("gym", HEADER)
    repo.create.assert_awaited_once_with(key="gym", label="🏋️ Gym", worksheet="gym")


@pytest.mark.asyncio
async def test_create_defaults_label_to_upper_key() -> None:
    repo, sheets = AsyncMock(), AsyncMock()
    repo.get.return_value = None
    sheets.read_header.return_value = None

    await _service(repo, sheets).create("gym")

    repo.create.assert_awaited_once_with(key="gym", label="GYM", worksheet="gym")


@pytest.mark.asyncio
async def test_create_refuses_existing_key_without_side_effects() -> None:
    repo, sheets = AsyncMock(), AsyncMock()
    repo.get.return_value = make_tracker(key="gym")

    with pytest.raises(TrackerError, match="already exists"):
        await _service(repo, sheets).create("gym")

    sheets.create_worksheet.assert_not_awaited()
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_refuses_existing_worksheet_and_points_at_attach() -> None:
    repo, sheets = AsyncMock(), AsyncMock()
    repo.get.return_value = None
    sheets.read_header.return_value = list(HEADER)

    with pytest.raises(TrackerError, match="/attach gym gym"):
        await _service(repo, sheets).create("gym")

    sheets.create_worksheet.assert_not_awaited()
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_propagates_sheets_error() -> None:
    repo, sheets = AsyncMock(), AsyncMock()
    repo.get.return_value = None
    sheets.read_header.side_effect = SheetsError("down")

    with pytest.raises(SheetsError):
        await _service(repo, sheets).create("gym")


@pytest.mark.asyncio
async def test_attach_registers_worksheet_with_contract_header() -> None:
    repo, sheets = AsyncMock(), AsyncMock()
    repo.get.return_value = None
    sheets.read_header.return_value = [*HEADER, ""]
    repo.create.return_value = make_tracker()

    await _service(repo, sheets).attach("my", " my-counter ", "MY")

    sheets.read_header.assert_awaited_once_with("my-counter")
    repo.create.assert_awaited_once_with(key="my", label="MY", worksheet="my-counter")
    sheets.create_worksheet.assert_not_awaited()


@pytest.mark.asyncio
async def test_attach_refuses_missing_worksheet_foreign_header_and_taken_key() -> None:
    repo, sheets = AsyncMock(), AsyncMock()
    repo.get.return_value = None
    service = _service(repo, sheets)

    sheets.read_header.return_value = None
    with pytest.raises(TrackerError, match="not found"):
        await service.attach("x", "nope")

    sheets.read_header.return_value = ["id", "username", "is_activated"]
    with pytest.raises(TrackerError, match=r"id \| username \| is_activated"):
        await service.attach("x", "users")

    with pytest.raises(TrackerError, match="empty"):
        await service.attach("x", "  ")

    repo.get.return_value = make_tracker(key="my")
    sheets.read_header.return_value = list(HEADER)
    with pytest.raises(TrackerError, match="already exists"):
        await service.attach("my", "my-counter")

    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_archive_unarchive_detach_delegate() -> None:
    repo = AsyncMock()
    repo.set_label.return_value = make_tracker(label="Mine")
    repo.set_archived.return_value = make_tracker()
    repo.delete.return_value = make_tracker()
    service = _service(repo)

    assert (await service.rename("my", " Mine ")).label == "Mine"
    await service.archive("my")
    await service.unarchive("my")
    await service.detach("my")

    repo.set_label.assert_awaited_once_with("my", "Mine")
    assert repo.set_archived.await_args_list == [(("my", True),), (("my", False),)]
    repo.delete.assert_awaited_once_with("my")


@pytest.mark.asyncio
async def test_mutations_on_unknown_key_raise() -> None:
    repo = AsyncMock()
    repo.set_label.return_value = None
    repo.set_archived.return_value = None
    repo.delete.return_value = None
    service = _service(repo)

    for call in (service.rename("x", "X"), service.archive("x"), service.unarchive("x"), service.detach("x")):
        with pytest.raises(TrackerError, match="No tracker 'x'"):
            await call


@pytest.mark.asyncio
async def test_check_worksheet_reports_problems() -> None:
    sheets = AsyncMock()
    service = _service(sheets=sheets)
    tracker = make_tracker()

    sheets.read_header.return_value = list(HEADER)
    assert await service.check_worksheet(tracker) is None

    sheets.read_header.return_value = None
    assert "not found" in (await service.check_worksheet(tracker) or "")

    sheets.read_header.return_value = ["Message", "Date"]
    assert "expected" in (await service.check_worksheet(tracker) or "")

    sheets.read_header.side_effect = SheetsError("APIError: 503")
    assert "503" in (await service.check_worksheet(tracker) or "")
