"""Every user-facing string in one place. English only (requirements §5); the table keeps lifelogger's shape."""

from __future__ import annotations

from collections.abc import Mapping

LOCALE = "en"

_MESSAGES: Mapping[str, Mapping[str, str]] = {
    "en": {
        "private_bot": "This is a private bot.",
        "not_allowed": "Not allowed",
        "admin_only": "This command is only available to bot admins.",
        "help_intro": (
            "<b>Tally</b> records events per day into a Google Sheet, one worksheet per tracker, "
            "and shows monthly summaries.\nTap a tracker, then a day; every tap is one row."
        ),
        "help_commands": (
            "/menu - pick a tracker and a day\n"
            "/stats - this month, all trackers\n"
            "/trackers - list trackers\n"
            "/new <key> [label] - create a tracker (and its worksheet)\n"
            "/attach <key> <worksheet> [label] - attach an existing worksheet\n"
            "/rename <key> <label> - change a label\n"
            "/archive <key>, /unarchive <key> - hide or show a tracker\n"
            "/detach <key> confirm - remove a tracker from the registry\n"
            "/timezone <IANA> - set your timezone\n"
            "/help - this text"
        ),
        "timezone_current": "Your timezone is {timezone}.\nSet it with /timezone Europe/Warsaw",
        "timezone_invalid": (
            "I do not recognize that timezone. Use an IANA name like Europe/Warsaw, Europe/Moscow, or UTC."
        ),
        "timezone_updated": "Timezone updated to {timezone}.",
        "menu_title": "What do you want to record?",
        "menu_empty": (
            "No trackers yet. Create one with <code>/new &lt;key&gt; [label]</code> or attach an existing "
            "worksheet with <code>/attach &lt;key&gt; &lt;worksheet&gt; [label]</code>."
        ),
        "choose_day": "Which day for <b>{label}</b>?",
        "button_today": "Today · {day}",
        "button_yesterday": "Yesterday · {day}",
        "button_back": "◀ Back",
        "button_stats": "📊 Stats",
        "button_saving": "⏳ saving…",
        "button_menu": "Menu",
        "button_prev_month": "◀ {month}",
        "button_next_month": "{month} ▶",
        "write_failed": "Could not write, try again",
        "stale_tracker": "That tracker is no longer available",
        "invalid_date": "That date is not valid",
        "recorded": "✅ {label} · {day} recorded.",
        "recorded_counts": " {month}: {total} (that day: {on_day})",
        "stats_title": "📊 <b>{month}</b>",
        "stats_empty": "No active trackers. Use /new or /attach.",
        "stats_tracker_line": "<b>{label}</b> — {total}",
        "stats_tracker_unavailable": "<b>{label}</b> — ⚠ unavailable",
        "stats_day_line": "  {day} · {count}",
        "stats_year_part": "{label} {total}",
        "stats_year_part_unavailable": "{label} ⚠",
        "stats_year_line": "Year {year}: {parts}",
    },
}


def t(key: str, **kwargs: object) -> str:
    return _MESSAGES[LOCALE][key].format(**kwargs)
