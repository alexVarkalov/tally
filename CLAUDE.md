# CLAUDE.md

## What this is
`tally` — a private Telegram bot for one user (the owner) that records **events per day** into a Google
Sheet and shows monthly summaries. Each kind of event is a **tracker**; each tracker is one worksheet in a
single spreadsheet. Tapping a tracker, then a day (today, yesterday, the day before) appends one row; several
rows on one day are normal, that is the tally. Trackers are dynamic (`/new`, `/attach`, `/rename`,
`/archive`, `/detach`) and live in Postgres; the rows live only in the sheet and are edited by hand there.
Async, python-telegram-bot v22, PostgreSQL/SQLAlchemy, gspread. No Mini App.

The brief is `docs/requirements.md` (wins over everything else); the recipe is `docs/playbook.md`.
Status and decisions: `docs/trackers/README.md`.

## Commands
```
uv sync --extra dev
uv run tally
uv run --extra dev ruff check . [--fix] | uv run --extra dev ruff format .
uv run --extra dev pytest [path::test | -k expr]
uv run --extra dev pre-commit install | uv run --extra dev pre-commit run --all-files
```
Requires Python 3.14+. Required env: `BOT_TOKEN`, `GOOGLE_SERVICE_ACCOUNT_FILE`, `GOOGLE_SPREADSHEET_ID`;
`.env.example` lists every variable with its default and a test diffs it against `Settings.from_env()`.

## Architecture
```
handlers  →  services  →  repositories  →  persistence (store mixins + ORM)
                ↓
        config, i18n, sheets.py (the only module that talks to Google)
```
1. Dependencies flow one way. `telegram` is imported only in `handlers/` and `__main__.py`.
2. Handlers are thin: guard `effective_user`/`effective_message`, `require_access()` (records the user and
   checks the allow-list), one service call, render. No SQL, no Sheets calls.
3. Every handler registers in `handlers/__init__.py::register_handlers()`; a test asserts the wiring.
4. Dependencies are wired once in `__main__.py::_post_init` onto `application.bot_data`
   (`settings`, `db`, `user_service`, `tracker_service`, `record_service`, `stats_service`).
5. Persistence returns frozen dataclasses (`BotUser`, `Tracker`); each store method is a sync `_x_sync`
   body run via `asyncio.to_thread`. Migrations are additive only (`create_all` + `ADD COLUMN IF NOT EXISTS`).
6. Pure domain modules, unit-tested without mocks: `services/records.py` (row builder, date choices),
   `services/stats.py` (parse rows, month summary, render), `services/dates.py` (English day/month names),
   `handlers/menu.py` (keyboard builders).
7. New feature = persistence → repository → service → handler, tests at each layer, one commit.

Modules by responsibility: `handlers/commands.py` (start, menu, help, timezone, admin), `handlers/callbacks.py`
(`rec:` and `menu:` callbacks, the recording flow with its per-chat lock), `handlers/stats.py` (`/stats`,
`stats:`), `handlers/trackers.py` (`/trackers`, `/new`, `/attach`, `/rename`, `/archive`, `/unarchive`,
`/detach`), `handlers/errors.py` (`on_error` and `report_error`), `sheets.py` (`SheetsClient`, `HEADER`,
`header_matches`, `escape_cell`, `SheetsError`).

### Conventions worth knowing before editing
- **Spreadsheet contract** (requirements §3): header `Year | Month | Day | Created at | Username | Comment`,
  counted day as three int cells, `Created at` as `YYYY-MM-DD HH:MM:SS` in the user's timezone, `Comment`
  always empty. `append_row` with `USER_ENTERED` and apostrophe escaping. Stats read the counted day from the
  three columns only. The bot never renames, clears or deletes a worksheet; `/new` is the only structural write.
- **Access**: `user_has_access = is_allowed or id in ADMIN_USER_IDS`; the owner is an admin. Non-users get
  "This is a private bot" on commands and a "Not allowed" alert on callbacks. `/users`, `/allow_user`,
  `/block_user` are admin-only. Trackers and the registry are global, not per user.
- **i18n**: every user-facing string is in `i18n.py` (`t(key, **kwargs)`, English only). Admin replies are
  plain strings in the handlers.
- **Telegram**: HTML parse mode, `html.escape()` on every dynamic value (labels are user input). Callback
  data `rec:<key>[:<YYYY-MM-DD>]`, `stats:<YYYY-MM>`, `menu:<action>`; one `CallbackQueryHandler` per prefix.
  Validate the key against the registry and the date with `date.fromisoformat()` before acting.
- **Time**: DB timestamps are UTC-aware; "today" and the date buttons are computed in the user's timezone
  (`/timezone`, default `DEFAULT_TIMEZONE`).
- **Errors**: `handlers/errors.py` logs every unhandled exception and pings the admins (one per error class
  per 10 minutes); handlers that catch a `SheetsError` themselves call `report_error` so the owner still
  hears about it. `httpx` logs at WARNING so the token never reaches the journal.
- **The date tap answers the callback after the append** (alert on failure, plain answer on success) and
  swaps the keyboard for a saving placeholder meanwhile; see `docs/trackers/README.md` for why.
- **Secrets**: `.env`, `data/` and `*service-account*.json` are gitignored. The repo is public: no IPs,
  hostnames, spreadsheet IDs, tokens or key files in code, docs, tests or commit messages.

### Production and operations
Runs on the owner's Raspberry Pi as `tally-bot.service` (systemd, `uv` venv, local PostgreSQL, no nginx).
Recipe: `docs/deployment.md`. Host facts (aliases, users, paths) are in the owner's private user-level
`~/.claude/CLAUDE.md`, not here. Update flow: pull → `uv sync --frozen` → restart the unit → check the journal.

### Testing
| Layer | Approach |
|---|---|
| `config.py` | `monkeypatch.setenv`/`delenv`; autouse fixture in `tests/conftest.py` sets the Google vars |
| `persistence/*Store` | `tests/persistence/fakes.py` (`FakeSession`, `FakeSessionFactory`, `FakeInsert`) against `_x_sync` |
| `repositories/` | `AsyncMock` `Database`, assert the delegated call |
| `services/` | `AsyncMock` repositories and `SheetsClient`; assert decisions |
| `handlers/` | `AsyncMock` services on a `SimpleNamespace` `context.application.bot_data`; `SimpleNamespace` update; patch `tally.handlers.common.record_user_seen` |
| `sheets.py` | `gspread.service_account` patched with `Mock`s |
| pure modules | plain unit tests, no mocks |

Every handler has no-message, access-denied and happy-path tests. Tests run in pre-commit and in CI; commit
only green.
