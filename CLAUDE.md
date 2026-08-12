# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HT-Manager: a Discord bot for HackerTroupe (a university security team) that curates/polls the next CTF, tracks participation, and syncs CTFTime results. Single-guild only — no multi-tenant scaffolding. The bot and hackertroupe.dev are intentionally independent — no shared API or database; Feature G (spec §13) is out of scope.

The full design spec is `docs/superpowers/specs/2026-08-04-ht-manager-design.md` — read it (or the relevant sections) before implementing any feature; it's the authoritative source of truth, not this file. `CHANGELOG.md` tracks what's actually been built.

## Commands

Python 3.13 required (`py -3.13` on this Windows/Git-Bash environment if multiple interpreters are installed — the plain `python`/`pip` on PATH may resolve to an unrelated older interpreter; verify with `py -3.13 -m pip show alembic` before assuming deps are installed).

```bash
# Setup
docker compose up -d --wait postgres
docker compose exec postgres createdb -U ht_manager ht_manager_test   # once; safe to re-run
pip install -e ".[dev]"

# Migrate dev DB (test DB is auto-migrated by the test suite itself)
export DATABASE_URL=postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager
alembic upgrade head

# Test / lint (TEST_DATABASE_URL defaults to .../ht_manager_test if unset)
pytest
pytest tests/test_config.py::test_settings_loads_from_env   # single test
ruff check .

# Run
python -m ht_manager.main

# Everything via Compose
docker compose up --build
```

Tests that don't touch the database run without Postgres — `_migrated_test_database` is deliberately *not* autouse, only `_engine` depends on it. That fixture also runs `alembic upgrade head` on a worker thread: `migrations/env.py` ends in `asyncio.run()`, which unsets the calling thread's current event loop, and on the main thread that silently destroys pytest-asyncio's session loop and breaks every async test after it.

**Migration reversibility is enforced, not just requested.** CI runs `alembic upgrade head && alembic downgrade base && alembic upgrade head && alembic check` — every migration needs a real `downgrade()` (never a no-op) and no drift between `Base.metadata` and the migration history. Never edit an already-applied migration; create a new one. `alembic.ini`/`migrations/env.py` read `DATABASE_URL` from the environment directly, not from `Settings`, so migrations run without full bot config.

**`Base.metadata` has a naming convention** (`src/ht_manager/db/base.py`) — any `CheckConstraint` (including ones SQLAlchemy generates implicitly from `Boolean`/`Enum` columns) needs an explicit `name=` or class definition raises at import time.

## Architecture

### The two consumers of a DB session

`db/session.py` exposes `create_engine(url)` / `create_session_factory(engine)`, deliberately decoupled from `Settings` (takes a plain URL). Two independent places wire this up, each disposing its own engine:

- **Bot**: `main.py` creates the engine, builds `HTManagerBot(settings, session_factory)`, disposes in a `finally` around `bot.start()`. Handlers reach the DB via `bot.session_factory`.
- **Tests**: `tests/conftest.py`'s `db_session_factory` fixture binds one connection inside a rolled-back transaction (`join_transaction_mode="create_savepoint"`), shared by the `db_session` and `bot` fixtures — so either can insert/commit freely with no persistent effect and no manual cleanup.

**Transaction ownership**: repositories and services never call `session.commit()`/`session.rollback()` — the caller owns the unit of work. This is **not** one transaction per multi-step sequence: spec §15.2's winner-resolution flow requires leaving a CTF in its last successfully-reached state on failure (not rolling back to the start) with idempotent per-step retries, and no transaction may be held open across a Discord API call. See the docstrings in `services/__init__.py` and `db/repositories/__init__.py`.

### Layering (target shape from the spec; `schemas/` is not populated yet)

```
src/ht_manager/
├── bot/            # discord.py only lives here (+ services/discord_resources.py)
│   ├── commands/   # thin: parse interaction, call a service, format reply
│   └── permissions.py   # is_admin() (plain predicate) + admin_only() (app_commands.check decorator)
├── services/       # business logic, one module per domain, never imports discord.py directly
├── jobs/           # scheduled jobs (APScheduler)
├── db/
│   ├── models/     # every model MUST be imported in models/__init__.py or it's invisible to
│   │                 Alembic autogenerate (enforced by tests/test_db_models_registration.py)
│   └── repositories/  # data access; no business rules
├── schemas/        # Pydantic request/response models
├── config.py       # Settings (pydantic-settings) + get_settings()
└── main.py         # bot entrypoint / composition root
```

**Service ownership is fixed and non-overlapping** (spec §22.1): `ctfs.py` (CTF metadata CRUD), `ctftime.py` (CTFTime HTTP client, isolated so its instability can't leak out), `polls.py` (poll lifecycle/winner selection — calls into `discord_resources.py` and `participation.py`, doesn't do their job), `participation.py` (participation rows/uniqueness), `discord_resources.py` (the **only** module allowed to call `discord.py` directly — role/forum/announcement operations), `results.py` (result persistence/dedup, delegates the CTFtime HTTP client to `ctftime.py`). Before adding logic to a service, check this table so it lands in the right one.

### CTFTime's API, as it actually behaves

Verified against the live API, not the docs — get this wrong and the sync fails silently rather than loudly:

- **There is no per-event results endpoint.** `/api/v1/events/<id>/results/` returns **404** (while `/api/v1/events/<id>/` returns 200). Results are published per *year*: `/api/v1/results/<year>/`.
- That payload is `{"<event_id>": {"title": ..., "scores": [{"team_id": int, "points": str, "place": int}]}}` — keyed by event id as a **string**, standings under `scores` (not `standings`), and `points` serialized as a **string** like `"6856.0000"`.
- `points` is that event's score (the `Score:` line in a summary), **not** the team's global rating points. It maps to `Result.score`; `rating_points` stays manual-only.
- One year is ~6 MB and covers every event, so `jobs/result_sync.py` groups its candidates by year and makes one request per year, not one per CTF. `list_awaiting_result_sync` bounds the candidate set (90 days, excludes hand-corrected results) so a quiet run costs zero requests.

A mocked test proves only that the parser matches the mock. When changing anything here, probe the real endpoint.

### Command permission enforcement

`admin_only()` (`bot/permissions.py`) is an `app_commands.check` decorator — apply it under `@tree.command`, not `is_admin()` called ad hoc inside a handler, so a denial raises `CheckFailure` uniformly. `HTManagerBot._on_app_command_error` (`bot/client.py`) branches on `CheckFailure` (WARNING log, "no permission" reply) vs. everything else (exception log, generic error reply), and guards the reply send itself against `discord.HTTPException`. `is_admin()` checks both role membership and `interaction.guild_id == settings.discord_guild_id` (spec §19).

### Config

`Settings` (`config.py`) is a single flat `pydantic-settings` model loaded from `.env` — no per-service config subsets. Required fields use `Field(min_length=1)` so an empty-but-present `.env` value fails validation loudly rather than passing an empty string downstream. `list[int]` fields (`ADMIN_ROLE_IDS`) use `Annotated[T, NoDecode]` + a `field_validator` — pydantic-settings JSON-decodes complex types by default on *both* the OS-env and `.env`-file loading paths, which breaks a plain comma-separated list; `NoDecode` disables that so the validator's manual split runs uniformly. `get_settings()` wraps construction errors in `SettingsError` with a pointer to `.env.example`; `main()` catches it and exits cleanly instead of a raw traceback.

`log_level` flows into `ht_manager/logging.py`'s `configure_logging()`, called once from `main()`. (Module named `logging.py` deliberately — safe under Python 3's absolute imports for every supported entrypoint, but avoid ever running a script directly as `python src/ht_manager/main.py`; that puts `src/ht_manager/` on `sys.path[0]` and shadows the stdlib `logging` module.)

### Docker Compose

`ht-manager-migrate` is a one-shot service (`alembic upgrade head`) that gates `ht-manager-bot` via `depends_on: condition: service_completed_successfully`. `DATABASE_URL` for the app services is **always** built from `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` pointed at the `postgres` service hostname — this is intentional (Compose always deploys and connects to its own local Postgres per spec §24's single-VM topology), not a bug; it does not honor an external `DATABASE_URL` override.

## Design constraints worth knowing before proposing changes

- **Single guild, one active CTF at a time.** Both are deliberate scope cuts (§6, §7.1, §31), not gaps — don't add multi-tenancy or concurrent-CTF handling.
- **No event bus / dispatcher.** Cross-service sequences (e.g. winner resolution) are explicit ordered function calls, documented in the spec (§15.2), not pub/sub. This was considered and declined.
- **Discord is a presentation layer; Postgres is the source of truth.** Participation/results tables never use Discord IDs as primary keys — roles and forum posts are temporary and admin-deletable, the historical record must outlive them.
- **File size**: 500 lines preferred, 1000 hard ceiling — split into a subpackage before crossing it (this is also what `Ruff`'s `C901` complexity check backs up).
- Milestones (`docs/superpowers/specs/...design.md` §25) are implemented one at a time, each ending in Ruff + pytest passing, a README update if workflow changed, and a commit — don't build ahead to a future milestone unless asked.
