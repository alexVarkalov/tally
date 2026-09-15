from __future__ import annotations

from datetime import date

from tally.handlers.menu import (
    choose_day_text,
    date_keyboard,
    date_label,
    saving_keyboard,
    stats_keyboard,
    tracker_menu_keyboard,
    tracker_menu_text,
)
from tests.helpers import make_tracker

TODAY = date(2026, 9, 15)


def _grid(markup) -> list[list[tuple[str, str]]]:  # type: ignore[no-untyped-def]
    return [[(b.text, b.callback_data) for b in row] for row in markup.inline_keyboard]


def test_tracker_menu_text() -> None:
    assert tracker_menu_text([make_tracker()]) == "What do you want to record?"
    assert "/new" in tracker_menu_text([]) and "/attach" in tracker_menu_text([])


def test_tracker_menu_keyboard_two_per_row_then_stats() -> None:
    trackers = [
        make_tracker(key="my", label="MY"),
        make_tracker(key="our", label="OUR"),
        make_tracker(key="gym", label="🏋️ Gym"),
    ]

    assert _grid(tracker_menu_keyboard(trackers, (2026, 9))) == [
        [("MY", "rec:my"), ("OUR", "rec:our")],
        [("🏋️ Gym", "rec:gym")],
        [("📊 Stats", "stats:2026-09")],
    ]
    assert _grid(tracker_menu_keyboard([], (2026, 1))) == [[("📊 Stats", "stats:2026-01")]]


def test_date_label() -> None:
    assert date_label(TODAY, TODAY) == "Today · Tue 15"
    assert date_label(date(2026, 9, 14), TODAY) == "Yesterday · Mon 14"
    assert date_label(date(2026, 9, 13), TODAY) == "Sun 13"


def test_date_keyboard_carries_iso_dates_and_back() -> None:
    choices = [date(2026, 9, 13), date(2026, 9, 14), TODAY]

    assert _grid(date_keyboard("my", choices, TODAY)) == [
        [
            ("Sun 13", "rec:my:2026-09-13"),
            ("Yesterday · Mon 14", "rec:my:2026-09-14"),
            ("Today · Tue 15", "rec:my:2026-09-15"),
        ],
        [("◀ Back", "menu:open")],
    ]


def test_choose_day_text_escapes_label() -> None:
    assert choose_day_text(make_tracker(label="A & B")) == "Which day for <b>A &amp; B</b>?"


def test_saving_keyboard_is_a_single_placeholder() -> None:
    assert _grid(saving_keyboard()) == [[("⏳ saving…", "menu:noop")]]


def test_stats_keyboard_navigation() -> None:
    assert _grid(stats_keyboard(2026, 9, (2026, 9))) == [
        [("◀ Aug 2026", "stats:2026-08")],
        [("Menu", "menu:open")],
    ]
    assert _grid(stats_keyboard(2026, 1, (2026, 9))) == [
        [("◀ Dec 2025", "stats:2025-12"), ("Feb 2026 ▶", "stats:2026-02")],
        [("Menu", "menu:open")],
    ]
    assert _grid(stats_keyboard(2025, 12, (2026, 1)))[0] == [
        ("◀ Nov 2025", "stats:2025-11"),
        ("Jan 2026 ▶", "stats:2026-01"),
    ]
