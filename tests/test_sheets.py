from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from gspread.exceptions import WorksheetNotFound

from tally import sheets as sheets_module
from tally.sheets import HEADER, SheetsClient, SheetsError, escape_cell, header_matches


def _client() -> SheetsClient:
    return SheetsClient(service_account_file="key.json", spreadsheet_id="sid")


def _fake_gspread(monkeypatch: pytest.MonkeyPatch, spreadsheet: SimpleNamespace) -> Mock:
    client = SimpleNamespace(open_by_key=Mock(return_value=spreadsheet), set_timeout=Mock())
    service_account = Mock(return_value=client)
    monkeypatch.setattr(sheets_module.gspread, "service_account", service_account)
    return service_account


def _worksheet(values: list[list[str]] | None = None) -> SimpleNamespace:
    rows = values if values is not None else [list(HEADER)]
    return SimpleNamespace(
        row_values=Mock(return_value=list(rows[0]) if rows else []),
        get_all_values=Mock(return_value=rows),
        append_row=Mock(),
    )


def test_escape_cell_only_touches_formula_triggers() -> None:
    assert escape_cell("=1+1") == "'=1+1"
    assert escape_cell("+48 123") == "'+48 123"
    assert escape_cell("-5 kg") == "'-5 kg"
    assert escape_cell("@alex") == "'@alex"
    assert escape_cell("plain text") == "plain text"
    assert escape_cell("") == ""


def test_header_matches_is_exact_but_ignores_trailing_blanks() -> None:
    assert header_matches(list(HEADER)) is True
    assert header_matches([*HEADER, "", ""]) is True
    assert header_matches([" Year ", "Month", "Day", "Created at", "Username", "Comment"]) is True
    assert header_matches(list(HEADER[:5])) is False
    assert header_matches([*HEADER, "Extra"]) is False
    assert header_matches(["id", "username"]) is False
    assert header_matches([]) is False


@pytest.mark.asyncio
async def test_append_row_opens_once_per_worksheet_and_escapes(monkeypatch: pytest.MonkeyPatch) -> None:
    my, our = _worksheet(), _worksheet()
    spreadsheet = SimpleNamespace(worksheet=Mock(side_effect=lambda name: {"my": my, "our": our}[name]))
    service_account = _fake_gspread(monkeypatch, spreadsheet)
    client = _client()

    await client.append_row("my", ["2026", "9", "15", "2026-09-15 14:39:01", "alex", ""])
    await client.append_row("my", ["2026", "9", "15", "2026-09-15 14:39:02", "=x", ""])
    await client.append_row("our", ["2026", "9", "14", "2026-09-15 14:39:03", "-a", ""])

    service_account.assert_called_once_with(filename="key.json")
    service_account.return_value.set_timeout.assert_called_once_with(20.0)
    assert spreadsheet.worksheet.call_args_list == [(("my",),), (("our",),)]
    assert my.append_row.call_args_list == [
        ((["2026", "9", "15", "2026-09-15 14:39:01", "alex", ""],), {"value_input_option": "USER_ENTERED"}),
        ((["2026", "9", "15", "2026-09-15 14:39:02", "'=x", ""],), {"value_input_option": "USER_ENTERED"}),
    ]
    our.append_row.assert_called_once_with(
        ["2026", "9", "14", "2026-09-15 14:39:03", "'-a", ""], value_input_option="USER_ENTERED"
    )


@pytest.mark.asyncio
async def test_read_header_returns_none_for_missing_worksheet_and_is_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worksheet = _worksheet([["id", "username"]])
    spreadsheet = SimpleNamespace(worksheet=Mock(side_effect=[WorksheetNotFound("gym"), worksheet, worksheet]))
    _fake_gspread(monkeypatch, spreadsheet)
    client = _client()

    assert await client.read_header("gym") is None
    assert await client.read_header("users") == ["id", "username"]
    assert await client.read_header("users") == ["id", "username"]
    assert spreadsheet.worksheet.call_count == 3


@pytest.mark.asyncio
async def test_read_rows_returns_records_keyed_by_header(monkeypatch: pytest.MonkeyPatch) -> None:
    worksheet = _worksheet(
        [
            [*HEADER, "", ""],
            ["2026", "9", "15", "2026-09-15 14:39:01", "alex", "", "x"],
            ["2026", "9"],
            [],
        ]
    )
    _fake_gspread(monkeypatch, SimpleNamespace(worksheet=Mock(return_value=worksheet)))

    rows = await _client().read_rows("my")

    assert rows == [
        {
            "Year": "2026",
            "Month": "9",
            "Day": "15",
            "Created at": "2026-09-15 14:39:01",
            "Username": "alex",
            "Comment": "",
        },
        {"Year": "2026", "Month": "9", "Day": "", "Created at": "", "Username": "", "Comment": ""},
        {"Year": "", "Month": "", "Day": "", "Created at": "", "Username": "", "Comment": ""},
    ]


@pytest.mark.asyncio
async def test_read_rows_rejects_foreign_header(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_gspread(monkeypatch, SimpleNamespace(worksheet=Mock(return_value=_worksheet([["id", "username"]]))))

    with pytest.raises(SheetsError, match="expected"):
        await _client().read_rows("users")


@pytest.mark.asyncio
async def test_read_rows_on_empty_worksheet_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_gspread(monkeypatch, SimpleNamespace(worksheet=Mock(return_value=_worksheet([]))))

    with pytest.raises(SheetsError):
        await _client().read_rows("empty")


@pytest.mark.asyncio
async def test_create_worksheet_adds_tab_with_header(monkeypatch: pytest.MonkeyPatch) -> None:
    created = SimpleNamespace(append_row=Mock())
    spreadsheet = SimpleNamespace(worksheet=Mock(), add_worksheet=Mock(return_value=created))
    _fake_gspread(monkeypatch, spreadsheet)
    client = _client()

    await client.create_worksheet("gym")
    await client.append_row("gym", ["2026", "9", "15", "t", "u", ""])

    spreadsheet.add_worksheet.assert_called_once_with(title="gym", rows=1, cols=len(HEADER))
    assert created.append_row.call_args_list[0] == ((list(HEADER),), {"value_input_option": "RAW"})
    spreadsheet.worksheet.assert_not_called()


@pytest.mark.asyncio
async def test_errors_are_wrapped_and_handles_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    worksheet = _worksheet()
    worksheet.append_row = Mock(side_effect=[RuntimeError("quota"), None])
    spreadsheet = SimpleNamespace(worksheet=Mock(return_value=worksheet))
    service_account = _fake_gspread(monkeypatch, spreadsheet)
    client = _client()

    with pytest.raises(SheetsError, match="RuntimeError: quota"):
        await client.append_row("my", ["x"])
    await client.append_row("my", ["x"])

    assert service_account.call_count == 2
    assert spreadsheet.worksheet.call_count == 2


@pytest.mark.asyncio
async def test_missing_worksheet_on_append_is_a_sheets_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_gspread(monkeypatch, SimpleNamespace(worksheet=Mock(side_effect=WorksheetNotFound("gone"))))

    with pytest.raises(SheetsError, match="WorksheetNotFound"):
        await _client().append_row("gone", ["x"])


@pytest.mark.asyncio
async def test_open_failure_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sheets_module.gspread, "service_account", Mock(side_effect=FileNotFoundError("key.json")))

    with pytest.raises(SheetsError, match="FileNotFoundError"):
        await _client().ensure_ready()
