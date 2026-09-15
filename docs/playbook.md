# Playbook: starting a new Telegram bot from this project

Everything that worked in `language-assistant` (vocab_bot), distilled into a reusable recipe. Copy this file
into the new repository as `docs/playbook.md` on day 0, then hand it to Claude Code together with a one-line
description of the bot and say "bootstrap the repo following the playbook". Replace `newbot` everywhere with
the real package name (snake_case) and `newbot-*` with the real service/hostname prefix.

Where this document says "copy from vocab_bot", the file in this repo is the reference implementation and
can be copied verbatim (path given each time). Where it says "adapt", the shape is right but the content is
domain-specific.

---

## 0) Day-0 decisions (answer before writing code)

Decide these first; each one changes the skeleton.

| Question | vocab_bot's answer | Notes |
|---|---|---|
| Private (allow-list) or public bot? | Private: new users blocked, admins bypass | Keep the allow-list even for "public" bots; flip the default of `is_allowed` instead. |
| One deployment per configuration, or per-user configuration? | One deployment per language pair | Per-deployment config = simpler code, one more service per variant. Choose per-user config only when variants will be many. |
| Does it need a Mini App (full-screen UI)? | Yes, mandatory | Only for interaction that chat buttons can't do well (cards, forms, lists). Adds a second process, nginx, TLS, a Node build. |
| External APIs? | DeepL via `httpx` | One `translate.py`-style module per API, called only from services. |
| Background jobs? | Due-card poll every 45 s | Use PTB's `job_queue`; state that must survive restarts goes to the DB, never to memory. |
| Locales? | `en`, `ru`, default from Telegram `language_code` | Decide the supported set on day 0; retrofitting i18n is painful. |
| Which host? | Existing DigitalOcean droplet (1 GB) | A third bot fits on the same droplet if RAM allows (see §9). |

---

## 1) Stack (pinned, with reasons)

- **Python 3.14+**, `uv` for deps and scripts, `hatchling` build backend. Never pip/venv by hand.
- **`python-telegram-bot[job-queue] >=22,<23`**, long polling (`run_polling(allowed_updates=Update.ALL_TYPES)`).
  Webhooks were never needed; polling survives NAT, restarts and IP changes.
- **`httpx`** for all outbound HTTP, one `AsyncClient` created in `post_init`, closed in `post_shutdown`.
- **PostgreSQL + SQLAlchemy 2.x ORM + `psycopg`** (v3). No SQLite fallback: the fake-session tests cover the
  store layer locally and Postgres-specific upserts (`on_conflict_do_update`) are used freely.
- **FastAPI + uvicorn** only when there is a Mini App, as an optional extra (`--extra api`).
- **Svelte 5 + Vite + TypeScript + vitest** for the Mini App frontend, built locally, static files rsynced.
- **ruff** (lint + format), **pytest + pytest-asyncio**, **pre-commit** running all three.
- No pydantic-settings, no python-dotenv, no Alembic (yet, see §11): a frozen `Settings` dataclass, a
  20-line `.env` loader and additive raw-SQL migrations were enough for two deployments.

`pyproject.toml` skeleton (copy from vocab_bot and rename):

```toml
[project]
name = "newbot"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "python-telegram-bot[job-queue]>=22.0,<23",
    "httpx>=0.27,<1",
    "sqlalchemy",
    "psycopg",
]

[project.optional-dependencies]
api = ["fastapi>=0.115,<1", "uvicorn[standard]>=0.30,<1"]
dev = ["fastapi>=0.115,<1", "pre-commit", "pytest", "pytest-asyncio", "ruff"]

[project.scripts]
newbot = "newbot.__main__:main"
newbot-api = "newbot.webapi.__main__:main"   # only with a Mini App

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
target-version = "py314"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

---

## 2) Repository skeleton

```
newbot/
├── CLAUDE.md                  # see §10; written on day 0, kept current
├── README.md                  # user-facing: features, quick start, config, deploy pointer
├── docs/
│   ├── playbook.md            # this file
│   └── <feature>/             # per big feature: README (status+decisions), architecture, api, implementation-plan, deployment
├── botfather_texts.txt        # /setcommands, /setdescription, /setabouttext texts, kept in sync with handlers
├── .env.example               # every variable, with a comment and its default; mirrors Settings.from_env()
├── .gitignore                 # .env, .env.*, data/, *.pdf, webapp/dist, webapp/node_modules, caches, .idea
├── .pre-commit-config.yaml    # ruff-check --fix, ruff-format, pytest (always_run)
├── .claude/settings.json      # allow-list of safe commands (uv run pytest, ruff, git status/diff/log, ls, cat…)
├── pyproject.toml
├── uv.lock                    # committed
├── scripts/                   # one-off data tools, each with tests
├── newbot/
│   ├── __main__.py            # main(): load .env → Settings.from_env() → Application.builder() → run_polling
│   ├── config.py              # Settings (frozen dataclass) + from_env() + load_dotenv_if_present()
│   ├── i18n.py                # t(), t_count(), SUPPORTED_LOCALES, resolve_user_locale()
│   ├── db.py                  # Database(UserStore, …): engine, session factory, init() with migrations
│   ├── <domain>.py            # pure logic modules (srs.py, lang_detect.py): no I/O, plain unit tests
│   ├── <external>.py          # one module per external API (translate.py)
│   ├── handlers/              # Telegram entry points; __init__.py::register_handlers() is the single wiring point
│   │   ├── __init__.py
│   │   ├── common.py          # record_user_seen, user_has_access, require_admin, formatting helpers
│   │   ├── commands.py        # /start, /menu, /locale, /timezone, admin commands
│   │   ├── callbacks.py       # one CallbackQueryHandler for all namespaced prefixes
│   │   ├── menu.py            # keyboard/text builders (pure, testable)
│   │   └── messages.py        # free-text handler
│   ├── webapi/                # only with a Mini App; sibling of handlers/, never imports it
│   │   ├── __main__.py        # uvicorn entry
│   │   ├── app.py             # create_app(settings, db=None): lifespan builds Database + services on app.state
│   │   ├── auth.py            # initData validation, pure (copy verbatim)
│   │   ├── deps.py            # get_current_user → BotUser; ApiError
│   │   ├── schemas.py         # pydantic response models
│   │   └── routes/            # one file per resource, one service call per route
│   ├── services/              # business logic; constructor-injected repos + Settings; never import telegram/fastapi
│   ├── repositories/          # thin async facades over Database, one per aggregate, domain-named methods
│   └── persistence/
│       ├── models.py          # SQLAlchemy ORM, *Record suffix
│       ├── types.py           # frozen dataclasses returned upward (BotUser, …)
│       ├── utils.py           # to_user()/to_x() mappers, utc_now()
│       └── <aggregate>.py     # XStore mixin: async def x() → asyncio.to_thread(self._x_sync)
├── tests/                     # mirrors the package tree 1:1 (tests/handlers/test_commands.py ↔ handlers/commands.py)
│   ├── conftest.py            # autouse env fixtures for mandatory settings
│   ├── helpers.py             # make_user() and other factories
│   ├── persistence/fakes.py   # FakeSession, FakeSessionFactory, FakeInsert
│   └── webapi/conftest.py     # make_init_data(), make_settings(), app fixture with AsyncMock services
└── webapp/                    # Mini App frontend (Svelte + Vite), only when needed
```

---

## 3) Architecture rules (the part worth being strict about)

```
handlers  ─┐
webapi    ─┴─►  services  →  repositories  →  persistence (store mixins + ORM)
                    ↓
            config, i18n, <external API modules>
```

1. **Dependencies flow one way.** `handlers/` and `webapi/` call services. Services call repositories.
   Repositories call `Database`. Nothing lower knows anything higher.
2. **`telegram` is imported only in `handlers/` and `__main__.py`. `fastapi` only in `webapi/`.** Helpers
   both entry points need (`user_has_access`, DTO builders) live in `services/`.
3. **Handlers are thin**: guard on `effective_user`/`effective_message` being `None`, call
   `record_user_seen()`, check `user_has_access()`, resolve locale, call one service method, render the
   reply. No SQL, no business rules, no external HTTP.
4. **Every handler registers in `handlers/__init__.py::register_handlers()`.** Conditional features register
   conditionally there (`if settings.x is not None`). A test asserts the wiring (`test_register_handlers.py`).
5. **Dependencies are wired once in `__main__.py::_post_init` and stored on `application.bot_data`**
   (`settings`, `db`, `http_client`, `<name>_service`). No module-level singletons; handlers read
   `context.application.bot_data["..."]`. The Mini App API does the same on `app.state` in the lifespan.
6. **Persistence returns frozen dataclasses**, never ORM objects. Each store method has a sync body
   (`_x_sync`, opens its own session, commits) wrapped by an async method using `asyncio.to_thread`. Sync
   SQLAlchemy in a thread was simpler than the async engine and is fast enough at this scale.
7. **Migrations are additive only**: `create_all` + `ALTER TABLE … ADD COLUMN IF NOT EXISTS` in
   `Database._init_sync`. Never drop or rename a column; leave a `# Legacy:` comment on the model instead.
8. **New feature = touch layers in order**: persistence → repository → service → handler and/or route,
   with tests at each layer, in one commit.

---

## 4) Cross-cutting conventions

### Configuration
- `Settings` is a `@dataclass(frozen=True)`; `Settings.from_env()` is the only place that reads `os.environ`.
- Validate hard requirements there and raise `ValueError` with a human message; `main()` prints it and
  exits with code 2. Everything else gets a default and a clamp (`_int_env(name, default=, minimum=)`).
- `load_dotenv_if_present()` reads `./.env` without overriding real env vars (systemd's `EnvironmentFile`
  wins). Copy from `vocab_bot/config.py`.
- `.env.example` lists every variable with a comment; keep it in lockstep with `from_env()` (a test can
  diff the two).
- Parse ID lists with `_parse_user_ids` (accepts `,` and `;`, skips junk).

### Users, access, admins
- Table `users` keyed by `telegram_id` with: `username`, `first_name`, `last_name`, `language_code`,
  `preferred_locale`, `timezone` (IANA string), `is_allowed` (default `False`), `created_at`, `updated_at`,
  `last_seen_at`. Copy `persistence/users.py`, `repositories/users.py`, `services/users.py`.
- `record_user_seen()` runs at the top of **every** handler and in the API auth dependency; it is an upsert
  that refreshes profile fields and `last_seen_at`.
- `user_has_access(user, admin_user_ids) = user.is_allowed or telegram_id in ADMIN_USER_IDS`. Admins can't
  be blocked while listed in the env var.
- Admin commands: `/users`, `/allow_user <id>`, `/block_user <id>` via `require_admin()`. These are
  English-only by design (admin = you).

### i18n
- All user-facing text through `t(locale, key, **kwargs)`; plurals through `t_count(locale, base_key, n)`
  with `_one/_few/_many` variants (Russian needs all three).
- Locale resolution: `preferred_locale` → Telegram `language_code` → `DEFAULT_LOCALE`.
- Adding a key = adding it for every locale in the same change; a test asserts key parity across locales.
- Never hardcode strings in handlers, except admin-only commands.

### Telegram specifics
- **HTML parse mode everywhere** (`reply_html`, `parse_mode="HTML"`), `html.escape()` every dynamic value.
  Markdown V2 escaping is a bug factory.
- **Callback data**: `prefix:arg1:arg2`, namespaced prefixes routed by one `CallbackQueryHandler` regex
  (`^(save|dismiss|menu):`). Parse with `split(":", maxsplit=N)`, validate `isdigit()` before `int()`.
  Keep payloads under 64 bytes: put IDs, not content, into callbacks; store content in a `pending` table
  with a TTL.
- Always `await query.answer()` early (Telegram shows a spinner until you do), `show_alert=True` for errors.
- Delete or edit your own prompt messages after the user acted so the chat stays clean.
- **Job queue**: `application.job_queue.scheduler.configure(timezone="UTC")`, `run_repeating(fn, interval,
  first=10, name="...")`. Inside a job, catch `Forbidden`/`BadRequest` per user (bot blocked, chat deleted)
  and treat as delivered so the log isn't flooded every tick; catch broad `Exception` per user and continue.
- **Reminders**: edge-triggered plus cool-down, state in the DB (`due_notified_at`), see
  `services/notifications.py`. Never send one message per item; consolidate ("N things to do → Open").
- Menu Button → Mini App is set on startup with `set_chat_menu_button`; Telegram clients cache it.

### Time
- Every timestamp is UTC-aware (`datetime.now(tz=UTC)`, `DateTime(timezone=True)` columns).
- Users store an IANA timezone string; convert only when rendering (`ZoneInfo`), fall back to UTC on
  `ZoneInfoNotFoundError`.

### Logging and errors
- `logging.basicConfig(level=INFO)` with the standard format; silence `httpx` to WARNING.
- `logger.exception()` in jobs and in the API auth path; handlers rely on PTB's default error logging.
- Mini App API errors are always `{"error": "<snake_code>", "message": "..."}` via one `ApiError`
  exception + three handlers (`ApiError`, `RequestValidationError`, `StarletteHTTPException`).

### Secrets and data hygiene
- `.env`, `.env.*` (except `.env.example`), `data/`, `*.pdf`, `webapp/dist` are gitignored. The repo is
  public: no IPs, hostnames, tokens, DB passwords or licensed datasets in git or docs. Those live in the
  operator's memory/notes and on the host.

---

## 5) Testing conventions

| Layer | Approach |
|---|---|
| `config.py` | `monkeypatch.setenv`/`delenv`; autouse fixture in `tests/conftest.py` sets mandatory vars |
| `persistence/*Store` | `tests/persistence/fakes.py` (`FakeSession`, `FakeSessionFactory`, `FakeInsert`) against `_x_sync` |
| `repositories/` | mock `Database` (`AsyncMock`) asserting the delegated call |
| `services/` | `AsyncMock` repositories; assert decisions, not SQL |
| `handlers/` | `AsyncMock` services on a `SimpleNamespace` fake `context.application.bot_data`; `SimpleNamespace` `Update` with `reply_text`/`reply_html` `AsyncMock`s; `monkeypatch.setattr(module, "record_user_seen", AsyncMock(return_value=make_user()))` |
| `webapi/` | `make_init_data()` builds signed initData; `create_app(settings, db=object())` + `AsyncMock` services on `app.state`; `httpx.AsyncClient(transport=ASGITransport(app))` |
| pure modules | plain unit tests, no mocks |

- `@pytest.mark.asyncio` on async tests; `tests/helpers.py::make_user(**overrides)` as the one user factory.
- Every handler gets at least: no-message returns, access-disabled path, happy path.
- Tests run on every commit via pre-commit (`always_run: true`, `pass_filenames: false`). Commit only green.
- Anything that needs a real Postgres is verified on the host after deploy (`journalctl`, `/api/health`).

`.pre-commit-config.yaml` (copy verbatim, bump the ruff rev):

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.2
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: uv run --extra dev pytest
        language: system
        pass_filenames: false
        always_run: true
```

---

## 6) Mini App module (only if §0 said yes)

Copy verbatim, then rename the package:

- `webapi/auth.py`: HMAC validation of Telegram `initData` (`WebAppData` secret, sorted `data_check_string`,
  `hmac.compare_digest`, `auth_date` max age). Pure, fully unit-tested (`tests/webapi/test_auth.py`).
- `webapi/deps.py`: `Authorization: tma <initData>` header → `parse_and_validate_init_data` →
  `user_service.record_seen()` → `user_has_access()` → `BotUser`. 401 `missing_auth`/`invalid_init_data`,
  403 `access_disabled`.
- `webapi/app.py`: `create_app(settings, db=None)`; `docs_url=None, redoc_url=None, openapi_url=None`;
  `/api/health`; routers under `/api`.
- `webapp/src/lib/telegram.ts` (typed `window.Telegram.WebApp` access, haptics), `api.ts` (fetch wrapper
  that adds the `tma` header), `i18n.ts`, screens `NotInTelegram`, `Blocked`.

Adapt: routes, schemas, screens. Rules:

- One service call per route; the route returns a pydantic schema built from a frozen dataclass.
- The API is a sibling of handlers, never imports `telegram`; the bot never imports `fastapi`.
- The frontend is a static bundle; API calls are same-origin `/api/...` (no CORS).
- `WEBAPP_URL` must be `https://` (Telegram refuses `http`), validated in `Settings.from_env()`.
- Document the contract in `docs/<feature>/api.md` before writing routes; tests are written against it.
- Design docs first: `docs/miniapp/README.md` (status + decisions log with dates), `architecture.md`,
  `api.md`, `implementation-plan.md` (phased, with acceptance criteria), `deployment.md`. This sequence
  worked: the whole Mini App shipped in two days because the plan was explicit.

---

## 7) Configuration and BotFather

- Required env: `BOT_TOKEN`, `DATABASE_URL`, `ADMIN_USER_IDS`, and whatever the bot's core API needs.
  With a Mini App: `WEBAPP_URL`, `WEBAPP_API_HOST=127.0.0.1`, `WEBAPP_API_PORT`, `WEBAPP_INITDATA_MAX_AGE`.
- `botfather_texts.txt` in the repo root holds the exact texts for `/setcommands` (user, feature-gated and
  admin sections), `/setdescription`, `/setabouttext`. Update it in the same commit as the handler change.
- Keep **privacy mode on** (default) unless the bot must read group messages.
- `/newapp` in BotFather gives a `https://t.me/<bot>/<app>` deep link to the Mini App; `/setdomain` is not
  needed for Mini Apps.
- New bot = new token = new `.env` = new database = new service pair. Never share a DB between bots.

---

## 8) Documentation conventions

- `CLAUDE.md` is the contract for Claude Code sessions: what the bot is, commands, architecture rules,
  conventions, testing table, production/ops summary without secrets. Write it on day 0 from the template
  in §10 and update it whenever a rule changes ("docs: bring every document in line" commits are normal).
- `README.md` is for a human running the bot: features, quick start, configuration table, usage, deploy
  pointer, development commands, project layout.
- `docs/<feature>/README.md` carries a **Status (date)** and **Decisions (date)** section; decisions are
  appended, not rewritten, so history survives.
- Commit messages: `<area>: <imperative summary>` (`bot:`, `webapp:`, `docs:`, `fix:`), one logical
  change per commit, tests included.

---

## 9) Deployment (DigitalOcean droplet, systemd, nginx)

The existing droplet already runs two deployments side by side; the new bot can be the third if RAM allows
(each Python process is roughly 60–100 MB resident; check `free -m` and add swap before a third pair).
Otherwise provision a second droplet with `doctl` exactly as in `docs/miniapp/deployment.md` §0.

Naming scheme per deployment (`<name>` = `newbot`, or `newbot-<variant>` for a second config):

| Thing | Value |
|---|---|
| Checkout | `/home/app/<name>` |
| Env file | `/home/app/<name>/.env` (mode 600, owner `app`) |
| Database | `<name_underscored>`, role `<name>bot`, password in `/home/app/.db_password_<name>` and `~/.pgpass` |
| Services | `<name>-bot.service`, `<name>-api.service` |
| API port | next free `808x` on `127.0.0.1` |
| Hostname | `<name>.<ip-dashed>.sslip.io` until a real domain exists |
| nginx site | `/etc/nginx/sites-available/<name>`, root `/var/www/<name>` |

Systemd unit template (`/etc/systemd/system/<name>-bot.service`; the API unit is identical with
`ExecStart=... -m newbot.webapi` and `After=... postgresql.service`):

```ini
[Unit]
Description=<Name> Telegram bot
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=app
WorkingDirectory=/home/app/<name>
EnvironmentFile=/home/app/<name>/.env
ExecStart=/home/app/<name>/.venv/bin/python -m newbot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Checklist for a new deployment on the existing host:

1. `sudo -u postgres createuser <role> && createdb -O <role> <db>`; set the password; add to `~/.pgpass`.
2. `git clone` into `/home/app/<name>`, `uv sync --frozen --extra api`, write `.env`, run once by hand.
3. Install both units, `systemctl enable --now`, check `journalctl -u <name>-bot -f`.
4. nginx: copy the `vocab` site, change `server_name`, `root`, proxy port; reuse the security-headers
   snippet and the `limit_req` zone (`docs/miniapp/deployment.md` §5). Bootstrap with a plain `:80` block,
   `certbot --nginx -d <host>`, then swap in the full config, `nginx -t && systemctl reload nginx`.
5. Build the frontend locally (`npm ci && npm run build`), `rsync -av --delete dist/ vocab:/var/www/<name>/`.
6. Add the new database to the nightly `pg_dump` cron (`deployment.md` §10).
7. BotFather texts, send `/start`, allow yourself with `/allow_user`, open the Mini App from the menu button.

Update flow (per checkout): `git pull` → `uv sync --frozen --extra api` → `sudo systemctl restart
<name>-bot <name>-api` → frontend rsync when `webapp/` changed. Migrations run on service start.

### How Claude operates the hosts

Host facts (IPs, SSH aliases, users, checkouts, service names, ports, hostnames, backup locations) are
**not in any repository**. They live in the operator's private user-level instructions file,
`~/.claude/CLAUDE.md`, which Claude Code loads in every project on that machine. A new project's Claude
therefore already knows the hosts; this repo's `CLAUDE.md` only needs to say "production: see the
user-level CLAUDE.md" plus this bot's own service names.

Conventions that make that work:

- **SSH aliases, never raw IPs**: `ssh vocab` (DigitalOcean droplet, user `app`, passwordless sudo) and
  `ssh pi` (Raspberry Pi on the home LAN). Keys and hosts are in `~/.ssh/config`.
- **One-shot remote commands**, not interactive sessions: `ssh vocab 'journalctl -u <name>-bot -n 200
  --no-pager'`, `ssh vocab 'systemctl status <name>-api --no-pager'`, `ssh vocab 'free -m'`.
- **Deploy = the update flow above run over SSH**, then a health check
  (`curl -s http://127.0.0.1:<port>/api/health` on the host, or the public `https://<host>/api/health`).
- **Frontend from the laptop**: the VPS has no Node; `npm run build` locally, `rsync -av --delete dist/
  vocab:/var/www/<name>/`.
- **Database**: `psql -h localhost -U <role> <db>` on the host reads the password from `~/.pgpass`; dumps
  are in `/home/app/backups`; take a `pg_dump -Fc` before any manual data change.
- **DigitalOcean itself** (create droplet, firewall, DNS, snapshots): `doctl` with an API token as in
  `docs/miniapp/deployment.md` §0, or the control panel. `doctl` is not installed on the laptop by default.
- **Raspberry Pi**: legacy home for chat-only bots (`tonus-bot`, `daily_counter_bot`, `lifelogger_bot`),
  plain systemd units with a `.venv`, local Postgres 15, no nginx or Mini Apps, LAN-only access. Use it for
  a bot that needs no public URL and can tolerate the home connection; use the droplet for anything with a
  Mini App or that must survive a home outage. `uv` on the Pi is in `~/.local/bin`, which is not on the
  non-interactive SSH PATH.
- **Permissions**: Claude Code's auto mode may refuse SSH commands against production as "production
  reads". Allow the read-only shapes explicitly in the new repo's `.claude/settings.json`, for example
  `Bash(ssh vocab 'systemctl status*)`, `Bash(ssh vocab 'journalctl*)`, `Bash(ssh pi 'systemctl status*)`;
  keep restarts and rsync behind a prompt.
- **Safety rules** (also in the user-level file): read freely; restart/pull/rsync only as part of a
  requested deploy; never drop, delete, restore over or disable anything without an explicit go-ahead.

---

## 10) CLAUDE.md template for the new repo

```markdown
# CLAUDE.md

## What this is
`newbot` — <one paragraph: what the bot does, who uses it, the one or two non-obvious design facts>.
Async, python-telegram-bot v22, PostgreSQL/SQLAlchemy. <Mini App: yes/no; if yes, point to docs/miniapp/README.md>.

## Commands
uv sync --extra dev [--extra api]
uv run newbot | uv run newbot-api
uv run --extra dev ruff check . [--fix] | ruff format .
uv run --extra dev pytest [path::test | -k expr]
uv run --extra dev pre-commit install | run --all-files

Requires Python 3.14+. Required env: BOT_TOKEN, DATABASE_URL, <...>. `.env.example` mirrors the defaults.

## Architecture
<the 4-layer diagram and the eight rules from playbook §3, trimmed to this bot's modules>

### Conventions worth knowing before editing
<i18n, access control, callback data, HTML replies, timestamps, layer order: playbook §4 in bullet form>

### Production and operations
<host, layout, service names, update flow, backups — no secrets; "ask the owner" for host specifics>

### Testing
<the table from playbook §5>
```

---

## 11) Ideas for the next bot (what I would change or add)

Ordered by expected payoff.

1. **Global error handler that pings the admin.** vocab_bot has none: an exception in a handler is only in
   `journalctl`. Add `application.add_error_handler(on_error)` that logs and sends a short message to
   `ADMIN_USER_IDS` with a rate limit (one per error class per 10 minutes). Cheap, and you learn about
   breakage from your phone.
2. **GitHub Actions CI** running `ruff check`, `ruff format --check`, `pytest`. Pre-commit is local-only
   and can be bypassed with `--no-verify`; CI is the real gate.
3. **Alembic from day 0.** Additive raw SQL works until the first rename, index or backfill. Setting Alembic
   up on an empty schema takes 20 minutes; retrofitting it onto a live DB takes an evening.
4. **A `deploy.sh`/Makefile target** that does pull → sync → restart → health check for a named checkout,
   so updating two or three deployments is one command per checkout instead of four.
5. **`/health` for the bot process too.** With a Mini App the API has `/api/health`; the bot has nothing.
   Cheapest option: the bot writes a heartbeat timestamp to the `users`-style table or a `bot_status` row on
   every poll tick, and the API health endpoint reports it. Alternative: systemd `WatchdogSec` + `sd_notify`.
6. **Real-Postgres tests in CI** (a `postgres` service container) for the store layer, in addition to the
   fakes. The fakes catch call shape, not SQL, and the one production bug that slipped through
   (`insert_card_if_missing` always reporting duplicates) was exactly a SQL-semantics bug.
7. **Mark users unreachable on `Forbidden`.** Right now a user who blocked the bot is retried after every
   cool-down. Store `unreachable_since` and skip them until they send a message again (which clears it).
8. **Extract a shared kit only at the third copy.** The user store, access control, i18n helper, `Settings`
   helpers, initData auth and test fakes are identical between bots. Copy them for the new bot; if a third
   bot appears, extract a private `tgbot-kit` package (installed from git via `uv`) rather than maintaining
   three copies. Two copies are cheaper than a premature library.
9. **Template repository.** After the new bot's skeleton is committed, mark a stripped copy as a GitHub
   template repo (or keep a `cookiecutter` dir). This playbook then becomes the template's README.
10. **Per-user rate limiting** on the free-text handler when the bot calls a paid API (DeepL characters
    are metered): a token bucket in memory per `telegram_id` plus a daily counter in the DB.
11. **Structured admin `/stats`**: users seen today/week, items created, external API usage. Ten lines of
    SQL and it answers "is anyone using this" without SSH.
12. **Keep polling, skip Docker.** Both were considered and rejected for good reasons on a 1 GB droplet:
    systemd + `uv` + a venv is simpler to operate and cheaper on RAM. Revisit only for multi-host.

---

## 12) Bootstrap checklist (do in this order)

1. BotFather: `/newbot`, save the token; note your Telegram ID for `ADMIN_USER_IDS`.
2. Create the repo, copy: this playbook, `.gitignore`, `.pre-commit-config.yaml`, `.claude/settings.json`,
   `pyproject.toml` (renamed), `.env.example` (trimmed).
3. Copy verbatim from vocab_bot: `config.py` (trim fields), `i18n.py` (trim keys), `db.py`,
   `persistence/{models(users only),types,utils,users}.py`, `repositories/users.py`, `services/users.py`,
   `handlers/{__init__,common,commands}.py` (start/menu/locale/timezone/admin), `__main__.py`,
   `tests/{conftest,helpers}.py`, `tests/persistence/fakes.py`, and their tests. Rename `vocab_bot` → `newbot`.
4. `uv sync --extra dev && uv run --extra dev pre-commit install && uv run --extra dev pytest` — green before
   any domain code.
5. Write `CLAUDE.md` (§10) and `README.md`; commit "init: skeleton from language-assistant playbook".
6. Domain code, layer by layer, with tests. Mini App per §6 if needed, with the design docs first.
7. Deploy per §9. Add the DB to backups. Update `botfather_texts.txt` and BotFather.
8. Write the ops facts (host, names, ports) into `~/.claude/CLAUDE.md` (the private user-level file, see §9
   "How Claude operates the hosts"), not into the repo.
