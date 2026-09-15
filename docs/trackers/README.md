# Trackers: status and decisions

The whole product is "trackers": dynamic, one worksheet each, tapped from an inline menu. The brief is
`docs/requirements.md`; this file records what was built and the decisions taken while building.

## Status (2026-09-15)

Built in one session, layer by layer, one commit per layer (`git log` is the changelog):

| Layer | Module | Tests |
|---|---|---|
| Google Sheets | `tally/sheets.py` (`SheetsClient`: `append_row`, `read_header`, `read_rows`, `create_worksheet`) | `tests/test_sheets.py` |
| Registry | `persistence/trackers.py`, `repositories/trackers.py`, `services/trackers.py` | mirrored |
| Rows | `services/records.py` (`build_row`, `date_choices`, `author_label`, `RecordService`) | `tests/services/test_records.py` |
| Stats | `services/stats.py` (`parse_rows`, `month_summary`, `render_month`, `StatsService`) | `tests/services/test_stats.py` |
| Bot | `handlers/menu.py`, `handlers/callbacks.py`, `handlers/stats.py`, `handlers/trackers.py` | mirrored |

Not yet done: deployment and the switch-over (requirements §10), which need the host and the owner. The
acceptance checklist in requirements §7 is to be walked through on the Pi after `/attach`.

## Decisions (2026-09-15)

- **The date tap answers the callback after the append, not before.** Requirements §4.2 asks for an
  immediate `query.answer()` and, on failure, an alert via `query.answer(show_alert=True)`; Telegram accepts
  only one answer per query. The alert matters more than the spinner, so the keyboard is swapped for a
  `⏳ saving…` placeholder immediately (visible feedback, and nothing left to double-tap), the row is appended
  under a per-chat lock, and the query is answered afterwards: plain on success, alert on failure. A second
  tap while the lock is held is answered silently and ignored. Sheets requests have a 20 s timeout so the
  answer always comes within Telegram's window.
- **`read_rows` verifies the header itself** (`get_all_values`, row 1 must be exactly the contract) and
  raises `SheetsError` otherwise. One code path therefore covers "worksheet renamed by hand" and "foreign
  header" for `/stats`, `/trackers` and the confirmation counts; `read_header` is only for `/new`, `/attach`
  and the startup check and never uses the cached worksheet handle.
- **Unavailable worksheets ping the admin.** `handlers/errors.py::report_error` (the same rate limit as
  the global error handler, one per error class per 10 minutes) is called when an append fails or a
  worksheet cannot be read, so the owner hears about a renamed tab from the phone while the other trackers
  keep working.
- **Management commands need access, not admin.** `/new`, `/attach`, `/rename`, `/archive`, `/unarchive`
  and `/detach` are guarded by the allow-list like the menu (trackers are global, the bot is single-user by
  design); only `/users`, `/allow_user` and `/block_user` are admin-only, as in lifelogger.
- **`/trackers` counts and warns in one Sheets call per tracker** (`fetch_days`): the month and total
  counts come from the same rows, and a `SheetsError` produces the `⚠ … unavailable: <reason>` line.
- **Labels are stored normalised** (whitespace collapsed, at most 32 characters); keys are validated with
  `^[a-z0-9_]{1,16}$` and never changed.
- **English date names are hard-coded** (`services/dates.py`) rather than taken from `strftime`, so the
  buttons and the stats do not depend on the host locale.
- **Timezone default comes from `DEFAULT_TIMEZONE`**, not UTC: `handlers/common.py::user_timezone` takes
  the settings, the only signature change in the copied user layer.
- **Shared kit deferred** (requirements §6.1): the copied user/config/test layer is kept byte-identical
  to lifelogger where possible (`db.py`, `persistence/users.py`, `repositories/users.py`, the fakes);
  `services/users.py` lost `set_locale` and `i18n.py` is a single-locale table with `t(key, **kwargs)`.
