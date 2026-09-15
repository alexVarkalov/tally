# Tally — requirements

Written 2026-09-15, revised the same day, for the Claude Code session that builds this bot in this (empty)
repository. It is the brief; `docs/playbook.md` (copied verbatim from the `language-assistant` playbook) is
the recipe. Where they disagree, this file wins. The sibling repo `lifelogger` (same owner, bootstrapped from
the same playbook the same day, at `~/projects/lifelogger` on the owner's laptop) is the source for the
files listed in §6.1, and only those. It is a different product ("a text message becomes a row"); its domain
code must not shape Tally.

Tally **replaces** an older bot, `daily_counter_bot` (2022). That code is deliberately not a reference: do
not open or copy from it. Everything the new bot must stay compatible with (the spreadsheet, the switch-over)
is written down here; where this document is silent, design it fresh.

All product decisions are settled (§8); there are no open questions. Ideas for later are in §12.

---

## 1) What the bot is

A private Telegram bot, **one user (the owner)**, that records **events per day** into a Google Sheet and
shows monthly summaries. Each kind of event is a **tracker**. Tapping a tracker, then a date (today,
yesterday, the day before) appends one row to that tracker's worksheet. Several rows on the same day are
normal (that is the tally). Stats show how many rows each day of a month has, per tracker.

Trackers are **dynamic**: the owner creates, renames, archives and lists them with bot commands, and each
tracker is one worksheet in the spreadsheet. The old bot had two hard-coded ones, `MY` and `OUR`, whose
worksheets hold 4.5 years of rows and are still in daily use; they are attached to the new bot as its first
two trackers.

That is the whole product. The value is the existing rows and the two-tap input from the phone. The build
must keep the spreadsheet contract (§3) exactly and make the bot maintainable (tests, layers, config,
deployment like the owner's other bots).

## 2) What the old bot does (behaviour only, for continuity)

- Flow: `/start` → inline buttons `OUR COUNTER` / `MY COUNTER` → three date buttons (day-2, day-1, today)
  plus `Show my data` → a date tap appends a row and confirms; `Show data` prints the current month's
  per-day counts and the total. The keyboard is gone afterwards and the user sends `/start` again.
- Data: one Google spreadsheet (owner's, ID in the private notes) with worksheets `my-counter`,
  `our-counter` and an old `users` tab that Tally ignores. A Google service account already has editor
  access to it; its key file is reused.
- It runs on the owner's Raspberry Pi as a systemd unit and keeps running until the switch-over in §10.

Behaviour worth keeping is in §4; known defects of the old bot, listed so they are not repeated, in §9.

## 3) Spreadsheet contract (MUST keep, this is the data)

One spreadsheet, referenced by ID (`GOOGLE_SPREADSHEET_ID`). **One worksheet per tracker.** Every tracker
worksheet, old or new, has this header in row 1; the two old ones have ~500 rows of history since 2022-01:

| Year | Month | Day | Created at | Username | Comment |
|---|---|---|---|---|---|
| 2026 | 9 | 15 | 2026-09-15 14:39:01 | owner_handle | |

- `Year`, `Month`, `Day`: the **counted day** as three integer cells (no zero padding, `Month` is `1`-`12`).
  This is the date the user tapped, not the write time. Rows are appended in write order, so the counted
  day is not monotonic (a "yesterday" row lands after today's).
- `Created at`: write time as `YYYY-MM-DD HH:MM:SS` in the user's timezone (§5), no microseconds.
- `Username`: Telegram handle, else full name, else the numeric id (copy `author_label` from lifelogger).
  Constant for a single user, still written for continuity.
- `Comment`: always written empty by the bot (`""`), reserved for hand edits in the sheet.
- Append with `value_input_option="USER_ENTERED"` so the numbers and the timestamp become real number/date
  cells like the existing rows. Escape any cell starting with `=` `+` `-` `@` with a leading apostrophe
  (copy `escape_cell`). Use `append_row`, never "count rows then insert at N+2".
- Read for statistics with `get_all_records()` (or `get_all_values()`); treat `Year`/`Month`/`Day` as ints
  whether they come back as int or str. Ignore rows where they are not parseable (blank trailing rows).
- **Rows are edited by hand in the sheet.** The owner's way to record something older than the date
  buttons offer is to record it as today and then change `Year`/`Month`/`Day` in the sheet. So stats must
  read the counted day from those three columns only, never infer it from `Created at` or from row order,
  and must not assume `Created at` is close to the counted day.
- **Worksheets are created only by `/new`** (§4.3), with exactly this header in row 1. The bot never
  renames, clears or deletes a worksheet, and never touches worksheets it does not know (the old `users`
  tab, anything the owner adds by hand). If a tracker's worksheet has gone missing or its header differs,
  log it, show `⚠` in `/trackers`, and reply "tracker not available" on use.
- The spreadsheet ID and the service-account key are secrets: `.env` and `data/` only, never in git,
  docs, tests or commit messages.

## 4) Functional requirements

### 4.1 Commands

| Command | Behaviour |
|---|---|
| `/start` | Records the user (upsert). The owner gets the menu (4.2); anyone else gets "This is a private bot" and nothing more. |
| `/menu` | The menu (4.2). |
| `/stats` | Month summary for the current month, all active trackers (4.4). |
| `/trackers` | List trackers (4.3). |
| `/new`, `/attach`, `/rename`, `/archive`, `/unarchive`, `/detach` | Tracker management (4.3). |
| `/timezone <IANA>` | Set the timezone; without argument show the current one. Copy from lifelogger. |
| `/users`, `/allow_user <id>`, `/block_user <id>` | Copied from lifelogger as they are (see §5). |
| `/help` | Two-line description and the command list. |

Keep `botfather_texts.txt` in sync. Replies to management commands are plain, short, English
(admin-style, like lifelogger's admin commands).

### 4.2 Recording flow (the main feature)

1. **Menu message**: text "What do you want to record?" and inline buttons, one per **active** tracker in
   position order, two buttons per row (labels can be long), callback `rec:<key>`. Last row: `📊 Stats`.
   With no active trackers the menu says so and points at `/new` and `/attach`.
2. **Tracker tapped**: the same message is edited to "Which day for <label>?" with a row of date buttons for
   the last `DAY_CHOICES` days (default 3) in the **user's timezone**, oldest first, today last. Labels:
   `Today · Mon 15`, `Yesterday · Sun 14`, `Sat 13` (weekday and day of month; the first two get the
   words). Below: `◀ Back`. Callback data carries the ISO date: `rec:<key>:<YYYY-MM-DD>`. The date is
   computed when the keyboard is built, so a tap on a stale keyboard after midnight still records the day
   that was shown.
3. **Date tapped**: `query.answer()` immediately; append the row; edit the message to a confirmation:
   `✅ <label> · Mon 15 Sep 2026 recorded. September: 4 (that day: 2)` where the numbers come from the
   month summary computed after the append; then **re-attach the tracker menu keyboard** under the
   confirmation so the next record is one tap away. No `/start` needed between records.
4. **Failure** (Sheets unreachable, worksheet missing): `query.answer(text="Could not write, try again",
   show_alert=True)`, keep the message and keyboard as they were, log the exception. Nothing is queued or
   retried.
5. **Stale callbacks**: a callback for an unknown or archived tracker key, or an invalid date, answers with
   a short alert and re-shows the menu. Validate the key against the registry and `date.fromisoformat()`
   before use.
6. A tap must never write twice: a second tap on the same message while the first append is in flight is
   ignored (simplest: a per-chat `asyncio.Lock` held across the append, and the keyboard swapped for a
   "saving…" placeholder meanwhile).

### 4.3 Tracker management

A tracker is: `key` (identifier, `[a-z0-9_]{1,16}`, unique, used in callback data and commands), `label`
(shown on buttons and in stats; any text up to 32 chars, emoji allowed; defaults to the key upper-cased),
`worksheet` (name of its tab), `position` (menu order; new trackers go last), `archived_at` (null = active),
`created_at`. Keys never change; labels do. The registry lives in Postgres (§5).

| Command | Behaviour |
|---|---|
| `/trackers` | One line per tracker: `MY (my, my-counter) · Sep: 4 · total 512`, archived ones under an "Archived" heading, `⚠` when the worksheet is missing or has a foreign header. |
| `/new <key> [label…]` | Creates a worksheet named `<key>` with the header (§3) and registers the tracker. Fails without side effects if the key exists or a worksheet named `<key>` already exists (say "use /attach"). |
| `/attach <key> <worksheet> [label…]` | Registers an existing worksheet. The worksheet must exist; if its header is not exactly the contract, refuse and show the header found. This is how `my-counter` and `our-counter` join: `/attach my my-counter MY`, `/attach our our-counter OUR`. |
| `/rename <key> <label…>` | Changes the label only. |
| `/archive <key>` / `/unarchive <key>` | Archived trackers leave the menu and the stats; their data stays. |
| `/detach <key>` | Removes the tracker from the registry. The worksheet is never touched; `/attach` brings it back. Requires the exact confirmation `/detach <key> confirm`. |

- Menu, stats and callback handlers read the registry on each request (one small query); no in-memory
  cache.
- Every key in a callback must resolve to an active tracker at tap time; archived/detached trackers give the
  stale-callback path (4.2 item 5).
- Creating a worksheet (`/new`) is the only structural write to the spreadsheet. `SheetsClient` gets
  `create_worksheet(name, header)` (gspread `add_worksheet` + header row) and `read_header(name)`.

### 4.4 Statistics

`/stats` and the `📊 Stats` button (`stats:<YYYY-MM>` in callback data, first shown for the current month in
the user's timezone) render **one message for all active trackers**, in position order:

```
📊 September 2026

MY — 4
  Sat 13 · 1
  Mon 15 · 3

OUR — 0

Year 2026: MY 31 · OUR 7
```

- Days listed in calendar order, only days with at least one row.
- Month total per tracker, then a year-to-date line for all trackers (all rows with that `Year`).
- Trackers whose worksheet is unavailable show `<label> — ⚠ unavailable` instead of numbers; one failure
  must not hide the others.
- Keyboard: `◀ Aug 2026` · `Oct 2026 ▶` (next absent when it is the current month), and `Menu`.
- Rendering is a pure function (`services/stats.py::render_month`) with unit tests; the handler only fetches
  rows per tracker and calls it.
- Reading all rows of every tracker per request is fine at this size (a few hundred rows per tracker, one
  user, a handful of trackers). Do not add caching or a database copy of the rows. If trackers grow past
  ~10, reading the three date columns only (`get_values("A:C")`) is the first optimisation.

## 5) Users, access, timezone, locale, registry storage

- **Single user by design.** Access is the lifelogger allow-list copied verbatim (`users` table,
  `is_allowed`, `ADMIN_USER_IDS` bypass, `/users`, `/allow_user`, `/block_user`). The owner's id goes into
  `ADMIN_USER_IDS`, so nobody needs allowing; everyone else is refused at `/start` and ignored on callbacks
  (`query.answer("Not allowed", show_alert=True)`). Keeping the layer as-is costs no new code and keeps Tally
  and lifelogger identical to operate. Consequences of "one user": trackers and the registry are **global**,
  not per user; stats are not filtered by `Username`.
- **PostgreSQL** holds two tables: `users` (exactly the lifelogger model) and `trackers` (4.3). Nothing
  else; the rows in the sheet never go into Postgres. Copy `db.py`, `persistence/`, `repositories/users.py`,
  `services/users.py` and their tests from lifelogger, then add `persistence/trackers.py::TrackerStore`,
  `repositories/trackers.py`, `services/trackers.py` in the same style (frozen `Tracker` dataclass,
  `_x_sync` in `asyncio.to_thread`, unique index on `key`).
- Rejected alternative, for the record: using the spreadsheet's tabs as the registry (tab = tracker). It
  needs a Sheets API call on every menu open and has nowhere to keep labels, order and archived state.
- Timezone: per user, IANA string, default `DEFAULT_TIMEZONE` from env (`Europe/Warsaw`). "Today" and the
  date buttons are computed in it; `Created at` is rendered in it.
- **English only.** Keep lifelogger's `i18n.py` shape with a single `en` table so every user-facing string
  lives in one file (`t("en", key)` or a thinner `t(key)`); no `/locale` command, no `DEFAULT_LOCALE`, no
  parity test, and `preferred_locale` stays in the copied `users` model as an unused legacy column.

## 6) Stack, architecture, conventions

Everything in `docs/playbook.md` §1–§5, §7, §8, §10, §11.1–11.2 applies. Concretely:

- Python 3.14, `uv`, `hatchling`; package `tally`, script `tally` (`tally.__main__:main`). Dependencies:
  `python-telegram-bot[job-queue]>=22,<23`, `gspread>=6.1,<7`, `sqlalchemy`, `psycopg`. Dev: `pytest`,
  `pytest-asyncio`, `ruff`, `pre-commit`. No Mini App, no FastAPI, no Docker.
- Repository `tally` (public, `alexVarkalov/tally`; no host facts, IDs, tokens or key files ever go in), default branch `main`. This `docs/` directory is
  already in the repo; the first commit is `init: skeleton from playbook`, then one commit per
  layer/feature, messages `<area>: <imperative summary>`.
- Layers: `handlers → services → repositories → persistence`, plus `sheets.py` (copy lifelogger's
  `SheetsClient`, generalised to take the worksheet name per call; keep the lock, the per-worksheet cached
  handle, `SheetsError`, `escape_cell`, `USER_ENTERED`; add `create_worksheet`, `read_header`,
  `read_rows`). `telegram` is imported only in `handlers/` and `__main__.py`.
- Domain modules, pure and unit-tested without mocks:
  - `services/records.py`: `build_row(tracker, day, now_local, user)`, `date_choices(today, n)`.
  - `services/stats.py`: `parse_rows(records) -> list[date]`, `month_summary`, `render_month`.
  - `services/trackers.py`: registry operations, key/label validation, `attach` header check (the Sheets
    calls go through an injected `SheetsClient`, mocked in tests).
  - `handlers/menu.py`: keyboard builders.
- Callback data, one `CallbackQueryHandler` per prefix family: `rec:`, `stats:`, `menu:`. Validate before
  acting, `await query.answer()` early, HTML parse mode with `html.escape()` on every dynamic value
  (labels are user input).
- Global error handler that logs and pings `ADMIN_USER_IDS` (rate-limited), copy `handlers/errors.py` from
  lifelogger. `httpx` logger at WARNING (the old bot logs the bot token into the journal on every poll).
- Wiring once in `__main__.py::_post_init` onto `application.bot_data`; at startup, open the spreadsheet
  once and check each registered tracker's worksheet and header, logged, not fatal.
- Tests mirror the package tree; every handler has no-message, access-denied and happy-path tests; a test
  asserts `register_handlers` wiring; a test diffs `.env.example` against `Settings.from_env()`.
  Pre-commit (ruff check --fix, ruff format, pytest) and GitHub Actions CI (ruff check, format --check,
  pytest).
- `CLAUDE.md` per playbook §10, `README.md` (features, quick start, config, deploy pointer),
  `docs/deployment.md` (host-agnostic, Raspberry Pi variant, copy lifelogger's and adapt),
  `docs/trackers/README.md` with status and decisions (playbook §8).

### 6.1 What to copy from lifelogger, and what not to

Copy verbatim, then rename `lifelogger` → `tally` and trim (keep their tests too, adjusted the same way):

| File(s) | Notes |
|---|---|
| `pyproject.toml`, `.pre-commit-config.yaml`, `.gitignore`, `.claude/settings.json`, `.github/workflows/ci.yml` | Rename, drop nothing else. |
| `config.py` | Keep `Settings`, `from_env`, `load_dotenv_if_present`, `_int_env`, `_parse_user_ids`; replace the fields with §6.2. |
| `db.py`, `persistence/{models,types,utils,users}.py`, `repositories/users.py`, `services/users.py` | The user layer, unchanged. Add the `trackers` model/store/repository/service alongside, in the same style. |
| `i18n.py` | Trim to the `en` table (§5). |
| `handlers/common.py`, `handlers/errors.py`, `handlers/commands.py` (start, menu, timezone, admin commands only) | Drop `/locale`. |
| `sheets.py` | Starting point for `SheetsClient`; generalise per §6 and replace lifelogger's `HEADER` with §3's. |
| `__main__.py` | Same wiring pattern, different services. |
| `tests/conftest.py`, `tests/helpers.py`, `tests/persistence/fakes.py` | Test scaffolding. |
| `docs/deployment.md` | Pi recipe; adapt names and add the Postgres `trackers` note. |

Do **not** copy or take inspiration from: `handlers/messages.py`, `services/logbook.py` (backdating
prefixes, `build_entry`; the one exception is the five-line `author_label` helper, which moves to
`services/records.py`), lifelogger's `HEADER` and `LogEntry`, its `CLAUDE.md`, `README.md`,
`docs/sheets/`, `botfather_texts.txt`. Tally's flow is callback-driven (§4.2); lifelogger's is free text.

This is the third copy of the user/config/test layer across the owner's bots. The playbook (§11.8) says to
extract a shared kit at the third copy; that is **deliberately deferred**: a shared package would add a
release step to every fix, and the copied layer is small and stable. Keep the copy byte-identical where
possible so an extraction later is a mechanical diff.

### 6.2 Configuration (`.env.example` must list all of these)

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `BOT_TOKEN` | yes | | Telegram bot token (new token at switch-over, §10). |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | yes | | Path to the service-account JSON; must exist at startup. |
| `GOOGLE_SPREADSHEET_ID` | yes | | The `/d/<ID>/` part of the spreadsheet URL. |
| `DATABASE_URL` | no | `postgresql+psycopg://tally:tally@localhost:5432/tally` | SQLAlchemy URL. |
| `ADMIN_USER_IDS` | no | empty | Comma/semicolon-separated Telegram ids; the owner's id goes here. |
| `DEFAULT_TIMEZONE` | no | `Europe/Warsaw` | IANA zone for users who have not set one. |
| `DAY_CHOICES` | no | `3` | Number of date buttons (clamped 1–7). |

No tracker configuration in the environment: trackers exist only in the registry.

## 7) Acceptance checklist

- [x] `uv run --extra dev pytest` green; ruff clean; CI green on GitHub.
- [ ] `/start` from a non-admin id → "private bot" reply; from the owner → the menu (empty-registry text).
- [ ] `/attach my my-counter MY` and `/attach our our-counter OUR` succeed; `/attach x users` is refused
      with the header shown; `/trackers` lists both with correct month and total counts.
- [ ] `/new gym 🏋️ Gym` creates a `gym` tab whose row 1 is the contract header, and `gym` appears last in
      the menu; `/new gym` again is refused; `/rename gym Gym` changes the button.
- [ ] Tap `MY` → date buttons in the user's timezone; tap yesterday → exactly one new row appears at the
      bottom of `my-counter` with `Year/Month/Day` of yesterday as numbers, `Created at` as a date cell,
      the handle in `Username`, empty `Comment`; confirmation shows the updated month count; the menu is
      back under the confirmation.
- [ ] `/archive our` removes it from the menu and stats; a tap on an old message's `OUR` button gives the
      stale alert; `/unarchive our` restores it. `/detach gym` without `confirm` does nothing.
- [ ] `/stats` matches a manual count of the current month in the sheet for every tracker, including days
      with several rows; `◀`/`▶` navigate months; the year line is correct.
- [ ] Rename the `gym` tab by hand in Sheets → `/trackers` shows `⚠`, `/stats` shows it unavailable, other
      trackers still work; the admin gets one error ping.
- [ ] Stop network to Google → alert "could not write", no crash, the keyboard survives.
- [x] `journalctl` shows no bot token anywhere.
- [ ] Two quick taps on the same date button produce one row.

## 8) Decisions already taken (do not reopen)

- Trackers are dynamic, managed by commands, stored in Postgres, one worksheet each (§4.3, §5).
- One user. The multi-user allow-list stays only because it is free; nothing is per-user except timezone.
- Sheets is the only store for rows; Postgres holds `users` and `trackers` only.
- `gspread` via `asyncio.to_thread`, service account, `USER_ENTERED` with apostrophe escaping.
- The bot never deletes, renames or clears worksheets. `/detach` is registry-only.
- Product name `tally`; entity name `tracker`; the two historic trackers keep keys `my` and `our` and their
  existing worksheet names.
- The old bot's Telegram handle and chat are reused; only the token changes (§10).
- Both historic trackers (`my`, `our`) are attached **active**; both are still in use.
- Default timezone `Europe/Warsaw`.
- English only (§5).
- No "other date" entry: three date buttons (`DAY_CHOICES=3`). Older events are recorded as today and
  corrected by hand in the sheet (§3), which the stats code must tolerate.
- The `Comment` column is never written by the bot and there is no note step in the flow.

## 9) Defects of the old bot not to repeat

- Callback handlers bypass the user check (only `/start` was guarded).
- `query.answer()` skipped on the tracker tap, so the client shows a spinner until timeout.
- Routing by substring (`'MY' in query.data`) and by splitting on `-`.
- `datetime.now()` in the server's local time; a timezone constant declared but unused.
- `Created at` written with microseconds; rows inserted at "record count + 2" (three API calls per tap
  instead of one, wrong if the sheet has blank rows).
- Keyboard removed after every action, forcing `/start` for each record.
- Month summary only for the current month, no navigation, days in insertion order rather than calendar
  order.
- Trackers hard-coded in the environment, one code path per tracker.
- Sync Google calls on the event loop; `httpx` INFO logging of the token; the allow-list as a CSV file next
  to the code.

## 10) Deployment and switch-over (host-agnostic; the private notes have the host facts)

- Host: the owner's Raspberry Pi, next to `lifelogger-bot`. Same recipe as `lifelogger/docs/deployment.md`:
  service user's home, `~/bots/tally` checkout, `~/.local/bin/uv sync --frozen`, `.env` and
  `data/service-account.json` (mode 600) copied out-of-band, local PostgreSQL role/db `tally`, systemd unit
  `tally-bot.service` with `EnvironmentFile=.env`, `ExecStart=<checkout>/.venv/bin/tally`,
  `Restart=always`. The armv7 note from that doc applies (`libffi-dev` for `cffi`).
- Reuse the existing service account and key (the spreadsheet is already shared with it). Nothing new in
  Google Cloud.
- **The old bot's Telegram identity is reused** (same handle, same chat history). At switch-over the owner
  revokes its token in BotFather (`/revoke`) and puts the new token into Tally's `.env`; the old process,
  which logs the token, is cut off by the revocation at the same moment. Update the command list,
  description and about text in BotFather from `botfather_texts.txt`.
- Switch-over, in order: revoke the token and deploy/start `tally-bot` with the new one; `/attach` the two historic worksheets; verify one record end to end in the sheet; then
  stop and disable the old `daily_counter_bot` unit and remove its checkout (owner's go-ahead required for
  the removal), and archive the old GitHub repository. Do not delete the old `users` worksheet.
- Afterwards the owner records the host facts in the private notes and adds the unit to the list of running
  bots there. The implementing session writes `docs/deployment.md` without hostnames, IPs or user names.

## 11) Resolved questions (2026-09-15, for the record)

Asked and answered by the owner the same day; the answers are folded into §8. Kept only so nobody reopens
them: keep both old trackers (yes, both active), default timezone (`Europe/Warsaw`), locales (English only),
entry of dates older than the buttons (no, hand-edit the sheet), `Comment` column (never written).

## 12) Ideas for later (not part of this build)

- **Undo**: after a record, an `↩ Undo` button that deletes the row just appended (the append response
  gives its range; delete that row if its cells still match).
- **Reorder**: `/order key1 key2 …` to set menu positions.
- **Other date**: `📅 Other…` button → the bot asks for `YYYY-MM-DD` as a text reply (rejected for now,
  the owner edits the sheet instead; only if that gets tedious).
- **Per-tracker stats**: `/stats <key>` with a longer horizon (last 12 months as a bar per month).
- **Daily reminder**: a job at a configurable local time, "Nothing recorded today", only if no tracker has a
  row for the day. Uses the job queue; state in the DB.
- **Streaks and gaps** (longest streak, days since last row) per tracker.
- **Export**: `/export <key> <year>` replies with a CSV of that year's rows.
- **Targets**: a per-tracker monthly goal shown as `4 / 10` in stats.
