# Deployment: Raspberry Pi, systemd, local Postgres

This bot polls Telegram and writes to Google, so it needs no public URL, nginx or TLS. One systemd unit, a
`uv` virtualenv, an `.env` and the service-account key are the whole deployment. This document is
host-agnostic on purpose: no IPs, hostnames or user names here (the public repo rule). The operator's
private notes hold those; every command below runs on the Pi over SSH unless marked *laptop*.

Naming used throughout:

| Thing | Value |
|---|---|
| Checkout | `/home/<user>/bots/tally` (the service user's home; `uv` lives in that user's `~/.local/bin`) |
| Service | `tally-bot.service` |
| Env file | `/home/<user>/bots/tally/.env` (mode 600) |
| Service-account key | `/home/<user>/bots/tally/data/service-account.json` (mode 600) |
| Database / role | `tally` / `tally` on the Pi's local PostgreSQL 15 |

The recipe is the one used for `lifelogger` on the same host; what is specific to replacing the 2022
`daily_counter_bot` is in step 7.

## 0) Prerequisites (once per host)

- `uv` installed for the service user (`curl -LsSf https://astral.sh/uv/install.sh | sh`). It is in
  `~/.local/bin`, which is **not** on the PATH of a non-interactive SSH command: call `~/.local/bin/uv`
  explicitly, or `source ~/.profile` first.
- Python 3.14 via uv: `~/.local/bin/uv python install 3.14`.
- On a Pi with a **32-bit (armv7) userland** there are no `cffi` wheels for 3.14, so it builds from source:
  `sudo apt-get install libffi-dev build-essential` first (`cryptography` itself ships an abi3 armv7 wheel).
- PostgreSQL running locally (`systemctl status postgresql`).
- Outbound HTTPS to `api.telegram.org`, `oauth2.googleapis.com` and `sheets.googleapis.com`.

## 1) Google side

**Existing setup (the normal case):** the service account and the spreadsheet already exist and the
spreadsheet is shared with the service account as Editor; nothing changes in Google Cloud. The key file
lives only in the deployed checkout (`data/service-account.json`, mode 600). When rebuilding the host, copy
it from a backup of that directory, or create a new key for the same service account in the Cloud Console
(old keys can be deleted there afterwards). The spreadsheet ID is the `/d/<ID>/` part of its URL.

**From scratch:**

1. Google Cloud Console: a project, enable **Google Sheets API** and **Google Drive API**.
2. IAM → Service Accounts → create one → Keys → *Add key* → JSON. Download it.
3. Create the spreadsheet. Share it with the service account's e-mail (`...@...iam.gserviceaccount.com`) as
   **Editor**. Copy the ID from the URL: `https://docs.google.com/spreadsheets/d/<ID>/edit`.

Worksheets are not configured anywhere: `/new <key>` creates one with the contract header
(`Year | Month | Day | Created at | Username | Comment`) and `/attach <key> <worksheet>` registers an
existing one whose row 1 is exactly that header. The bot never renames, clears or deletes a worksheet.

## 2) Database

```bash
# a generated password keeps it out of the shell history; it lands only in ~/.pgpass and .env
PW=$(openssl rand -hex 16)
sudo -u postgres psql -qc "CREATE ROLE tally LOGIN PASSWORD '$PW'"
sudo -u postgres createdb -O tally tally
# let psql on the host find the password: ~/.pgpass, mode 600
echo "localhost:5432:tally:tally:$PW" >> ~/.pgpass && chmod 600 ~/.pgpass
psql -h localhost -U tally tally -c "select 1;"
```

Tables are created on first start (`Database.init()`): `users` (allow-list, timezone) and `trackers` (the
registry: key, label, worksheet, position, archived_at). The recorded rows are **not** in Postgres; they
live only in the spreadsheet. Later columns are added with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on
every start, so there is no separate migration step.

## 3) Checkout and environment

```bash
mkdir -p ~/bots && cd ~/bots
git clone <repo-url> tally && cd tally
~/.local/bin/uv sync --frozen                            # production deps only, from uv.lock
mkdir -p data && chmod 700 data
```

Copy the secrets out-of-band (never via git), from the *laptop*:

```bash
scp .env                 <host>:bots/tally/.env
scp service-account.json <host>:bots/tally/data/service-account.json
ssh <host> 'chmod 600 bots/tally/.env bots/tally/data/service-account.json'
```

`.env` contents (see `.env.example` for every variable):

```env
BOT_TOKEN=...
ADMIN_USER_IDS=<your telegram id>
DATABASE_URL=postgresql+psycopg://tally:<password>@localhost:5432/tally
GOOGLE_SERVICE_ACCOUNT_FILE=/home/<user>/bots/tally/data/service-account.json
GOOGLE_SPREADSHEET_ID=<id>
DEFAULT_TIMEZONE=Europe/Warsaw
DAY_CHOICES=3
```

Use the absolute path for the key file: systemd sets `WorkingDirectory`, but an absolute path also works
when you run the bot by hand from elsewhere.

## 4) First run by hand

```bash
cd ~/bots/tally && .venv/bin/tally
```

Expected in the log: PTB's "Application started", no `SheetsError` traceback, then one line per registered
tracker (`tracker 'my' → worksheet 'my-counter' ok`) and `N tracker(s) registered` (0 on a fresh database).
Send `/start` from the admin account: the reply is the menu (empty-registry text at first). Then
`/attach my my-counter MY`, tap `MY`, tap a day: the row appears at the bottom of the worksheet with
`Year/Month/Day` as numbers and `Created at` as a date cell. Then `Ctrl+C`.

If another process still polls with the same token (an old deployment, a local test run), stop it first or
the two will swallow each other's updates.

Typical first-run failures:

| Symptom | Cause |
|---|---|
| `BOT_TOKEN is required` / `GOOGLE_... is required` (exit 2) | `.env` missing or a key empty |
| `GOOGLE_SERVICE_ACCOUNT_FILE does not exist` | wrong path in `.env` |
| `SheetsError: SpreadsheetNotFound` | wrong ID, or the sheet is not shared with the service-account e-mail |
| `SheetsError: APIError ... 403` | Sheets API or Drive API not enabled in the Google project |
| `tracker 'x' unavailable: worksheet ... not found` | the tab was renamed by hand; `/detach x confirm` and `/attach` under the new name |
| `psycopg.OperationalError` | role, password or database from step 2 wrong |

## 5) systemd unit

`/etc/systemd/system/tally-bot.service` (replace `<user>`):

```ini
[Unit]
Description=Tally Telegram bot
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=<user>
WorkingDirectory=/home/<user>/bots/tally
EnvironmentFile=/home/<user>/bots/tally/.env
ExecStart=/home/<user>/bots/tally/.venv/bin/tally
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tally-bot
systemctl status tally-bot --no-pager
journalctl -u tally-bot -f
```

`EnvironmentFile` wins over `.env` parsing inside the app (the loader never overrides existing variables),
so systemd is the source of truth in production.

## 6) BotFather and access

Paste the texts from `botfather_texts.txt` into `/setcommands`, `/setdescription`, `/setabouttext`. Keep
privacy mode on (default). Admins listed in `ADMIN_USER_IDS` have access immediately; everyone else gets
"This is a private bot" until `/allow_user <telegram_id>` (their ID shows up in `/users` after they press
`/start`). Trackers are global: every allowed user sees the same menu.

## 7) Switch-over from the legacy `daily_counter_bot` (done 2026-09-15, kept as history)

The 2022 bot ran on the same Pi under its own service user with two hard-coded counters whose worksheets
(`my-counter`, `our-counter`) hold the history and stay in use. What the switch-over involved:

1. **Secrets reused, not recreated.** The service-account key was copied from the old checkout into
   `data/service-account.json` (that account is the one the spreadsheet is shared with). The old bot opened
   the spreadsheet by *title*, so the ID for `GOOGLE_SPREADSHEET_ID` was resolved once with a read-only
   gspread call: `gspread.service_account(filename=...).open("<title>").id`. `ADMIN_USER_IDS` came from the
   sibling bot's `.env` on the same host.
2. **Same bot identity, new token.** BotFather `/revoke`; the old process failed with
   `InvalidToken: Unauthorized` from that moment (no polling conflict), the new token went into `.env`, then
   steps 4–5. The unit was installed before the token existed and started only afterwards.
3. `/attach my my-counter MY` and `/attach our our-counter OUR`, `/trackers`, then one record verified in
   the sheet (`Year/Month/Day` as numbers, `Created at` a date cell) and in the chat confirmation.
4. Buttons left in the chat by the old bot carried foreign callback data; the first tap on one of them was
   dropped silently. Fixed the same day with a catch-all callback handler (alert + menu) before retrying.
5. `sudo systemctl disable --now daily_counter_bot`; a tarball of `/opt/daily_counter_bot` went to
   `~/backups` (mode 600, it contains the key and the old `users.csv`), then the directory and the unit file
   were removed and `daemon-reload` run. The service user was left in place. The GitHub repository was
   archived. The old `users` worksheet in the spreadsheet stays; the bot ignores it.

## 8) Update flow

```bash
cd ~/bots/tally && git pull origin main && ~/.local/bin/uv sync --frozen \
  && sudo systemctl restart tally-bot && sleep 3 && systemctl status tally-bot --no-pager
```

Migrations run on start. Nothing else to deploy: no frontend, no nginx.

## 9) Operating

```bash
systemctl status tally-bot --no-pager
journalctl -u tally-bot -n 200 --no-pager          # -f to follow
psql -h localhost -U tally tally -c "select key, label, worksheet, position, archived_at from trackers order by position;"
psql -h localhost -U tally tally -c "select telegram_id, username, is_allowed, timezone, last_seen_at from users order by last_seen_at desc;"
free -m; df -h /
```

- Unhandled exceptions, failed appends and unavailable worksheets are logged **and** sent to every admin as
  a Telegram message (at most one per error class per 10 minutes).
- A failed append shows the alert "Could not write, try again" and leaves the buttons in place; nothing is
  queued or retried.
- The journal never contains the bot token: `httpx` logs at WARNING.
- Google Sheets API quota: 300 write requests per minute per project. A handful of taps a day is nowhere near.

## 10) Backups

The sheet is the data: Google keeps its own version history (File → Version history) and you can download
it any time. The Postgres tables hold the allow-list, timezones and the tracker registry, all rebuilt in a
minute with `/allow_user` and `/attach`, so a nightly dump is optional:

```bash
# crontab -e on the Pi, 03:15 every day, 30-day retention
15 3 * * * pg_dump -Fc -h localhost -U tally tally > ~/backups/tally_$(date +\%F).dump && find ~/backups -name 'tally_*.dump' -mtime +30 -delete
```

Restore into an empty database with the service stopped: `pg_restore --no-owner --no-privileges -d tally <file>`.
