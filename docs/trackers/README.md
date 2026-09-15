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

Deployed the same day on the owner's Raspberry Pi as `tally-bot.service` (recipe: `docs/deployment.md`).
Switch-over completed 2026-09-15: token rotated in BotFather, both historic worksheets attached
(`/attach my my-counter MY`, `/attach our our-counter OUR`), one record verified end to end in the sheet
(three integer cells, a real date cell, the handle, an empty comment; confirmation showed the right counts),
`daily_counter_bot` stopped, disabled and removed from the host, its GitHub repository archived.

Acceptance (requirements §7) verified on the host: tests/CI green; the owner's `/start` menu; both attaches
with correct `/trackers` counts; the record flow (today) with the menu re-attached; clean journal (no token,
no warnings). Only unit-tested so far, to be tried when convenient: `/start` from a non-admin id, `/new` on a
fresh tab, `/attach` against the foreign `users` tab, archive/unarchive, the hand-renamed tab, cutting the
network, and the double tap.

One defect found during the switch-over and fixed before the first record: buttons left in the chat by the
old bot reached Tally with foreign callback data and were dropped silently (a spinner, no reply). A catch-all
`CallbackQueryHandler` now answers them with an alert and the menu.

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
- **Unknown callback data is answered, not dropped.** A catch-all `CallbackQueryHandler` registered last
  alerts "button from an older version" and re-shows the menu; without it a tap on one of the old bot's
  buttons (same Telegram identity, old messages still in the chat) left the client spinning.
- **Shared kit deferred** (requirements §6.1): the copied user/config/test layer is kept byte-identical
  to lifelogger where possible (`db.py`, `persistence/users.py`, `repositories/users.py`, the fakes);
  `services/users.py` lost `set_locale` and `i18n.py` is a single-locale table with `t(key, **kwargs)`.
