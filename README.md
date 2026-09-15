# Tally

A private Telegram bot that tallies events per day into a Google Sheet and shows monthly summaries.

Each kind of event is a **tracker**, and each tracker is one worksheet in your spreadsheet. Tap a tracker,
then a day (today, yesterday, the day before): one row is appended. Several rows on the same day are the
tally. `/stats` shows, per tracker, how many rows each day of a month has, with month and year totals.

## Features

- Two-tap recording from the phone: tracker → day → `✅ recorded`, menu stays under the confirmation.
- Dynamic trackers: `/new`, `/attach` (an existing worksheet), `/rename`, `/archive`, `/unarchive`, `/detach`.
- Monthly statistics for all trackers with month navigation; days are read from the sheet's own
  `Year/Month/Day` columns, so rows edited by hand in the sheet count correctly.
- Rows are appended with `USER_ENTERED`, so numbers and timestamps become real cells.
- Single user by design: an allow-list with admin bypass, everyone else is refused.
- Per-user timezone (`/timezone Europe/Warsaw`).
- Unhandled errors are logged and sent to the admins (rate-limited).

## Quick start

```bash
uv sync --extra dev
cp .env.example .env            # fill in BOT_TOKEN, GOOGLE_*, ADMIN_USER_IDS
uv run tally
```

Needs Python 3.14+, a PostgreSQL database (see `DATABASE_URL`) and a Google service account with editor
access to the spreadsheet. Send `/start` from the admin account, then `/new <key> [label]` or
`/attach <key> <worksheet> [label]` to get the first tracker.

## Configuration

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `BOT_TOKEN` | yes | | Telegram bot token from @BotFather |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | yes | | Path to the service-account JSON key; must exist at startup |
| `GOOGLE_SPREADSHEET_ID` | yes | | The `/d/<ID>/` part of the spreadsheet URL |
| `DATABASE_URL` | no | `postgresql+psycopg://tally:tally@localhost:5432/tally` | SQLAlchemy URL |
| `ADMIN_USER_IDS` | no | empty | Comma/semicolon-separated Telegram ids; put your own here |
| `DEFAULT_TIMEZONE` | no | `Europe/Warsaw` | IANA zone for users who have not set one |
| `DAY_CHOICES` | no | `3` | Number of date buttons (clamped 1–7) |

## Spreadsheet contract

Every tracker worksheet has this header in row 1: `Year | Month | Day | Created at | Username | Comment`.
`Year/Month/Day` are the counted day as integers, `Created at` is the write time in your timezone,
`Comment` is never written by the bot (reserved for hand edits). Worksheets are created only by `/new`; the
bot never renames, clears or deletes a worksheet, and never touches tabs it does not know.

## Commands

| Command | What it does |
|---|---|
| `/start`, `/menu` | The tracker menu: tap a tracker, then a day |
| `/stats` | This month for every active tracker, with month navigation |
| `/trackers` | List trackers with this month's and total counts |
| `/new <key> [label]` | Create a tracker and its worksheet |
| `/attach <key> <worksheet> [label]` | Register an existing worksheet (its header must match the contract) |
| `/rename <key> <label>` | Change the label |
| `/archive <key>`, `/unarchive <key>` | Hide from or restore to the menu and stats; data stays |
| `/detach <key> confirm` | Remove from the registry; the worksheet is untouched |
| `/timezone [IANA]` | Show or set your timezone |
| `/users`, `/allow_user <id>`, `/block_user <id>` | Admin: the allow-list |

## Deployment

See `docs/deployment.md` (systemd unit, `uv` venv, local PostgreSQL; written for a Raspberry Pi).

## Development

```bash
uv run --extra dev pytest
uv run --extra dev ruff check . && uv run --extra dev ruff format .
uv run --extra dev pre-commit install
```

Layout: `tally/handlers` (Telegram), `tally/services` (logic), `tally/repositories` and `tally/persistence`
(Postgres), `tally/sheets.py` (Google Sheets). Tests mirror the package tree under `tests/`.
See `CLAUDE.md` for the architecture rules and `docs/requirements.md` for the full brief.
