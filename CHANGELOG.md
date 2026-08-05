# Changelog

All notable changes to HT-Manager are documented here, milestone by
milestone, per `docs/superpowers/specs/2026-08-04-ht-manager-design.md`.

## [Unreleased]

### Scope change — dropped the website API

Removed `api/` (FastAPI app, `/health`, session dependency) and its tests,
the `ht-manager-api` Compose service, `fastapi`/`uvicorn` dependencies, and
`PUBLIC_API_ORIGINS` config. The bot and hackertroupe.dev are independent —
Feature G (spec §13, read-only API for the website) is out of scope; the
bot no longer needs to coordinate schema/deployment with a public API.

### M1 — CTF Data

- Added `ctfs` and `audit_log` tables (migration `0002`): `CTF` model with
  the `CTFStatus` lifecycle enum (spec §15) stored as a native Postgres
  enum, and an append-only `AuditLog` model (spec §14.2).
- `services/ctfs.py`: draft creation, metadata updates, draft-only hard
  delete (spec §14.3 — only `DRAFT` CTFs have no history to protect), and
  `transition()` enforcing the exact transition table from spec §15.1 —
  anything not explicitly listed there is rejected. Every mutation writes
  an `audit_log` row with a before/after snapshot of the changed fields.
- `services/ctftime.py`: an isolated `CTFTimeClient` (spec §10) wrapping
  CTFTime's `/events/{id}/` endpoint, with timeout, bounded retries with
  backoff on transport errors/5xx, and parsing covered by fixture-based
  tests so future CTFTime API drift is caught in one place.
- `/addctf` and `/editctf` admin commands, thin translation layers over
  `services/ctfs.py` per the command-handler convention established in M0.1.
- `db/repositories/ctfs.py` and `db/repositories/audit_log.py` for the new
  tables, following the existing repository/service/transaction-ownership
  split.

### M0.3 — Foundation Hardening, round 3

Fix wave addressing the one Critical/blocking finding from the M0.2
re-review (spec-compliance and technical-debt, both empirically verified
with live test probes), before starting M1.

- Fixed `api_client`: it used FastAPI's synchronous `TestClient`, which
  drives the app from a separate thread with its own event loop, breaking
  the isolated-session override the moment a route actually awaits it
  (asyncpg connections are bound to the loop that created them). Replaced
  with an `httpx.AsyncClient` over `ASGITransport` sharing pytest-asyncio's
  loop. Also closed a second escape hatch: `app.state.session_factory` now
  points at the isolated factory too, not just the `get_session` DI
  override, so code reading `request.app.state` directly can't bypass
  isolation. New `test_api_session_wiring.py` proves a DB-touching request
  actually works through the fixture — the previous suite only ever
  exercised `/health`, which touches no DB, so the override was registered
  but never invoked.
- Corrected the M0.2 transaction-ownership docstrings: they described one
  transaction per multi-step sequence, which contradicts spec §15.2's
  actual model (partial-progress-preserving, per-step, idempotent retries,
  no transaction held open across a Discord API call).
- Added direct tests for `HTManagerBot._on_app_command_error` (both the
  `CheckFailure` and generic-error branches, the `followup` vs.
  `response.send_message` paths, and the `HTTPException` guard) and for
  `admin_only()`'s denial path — previously only the allow path was tested.
- Documented the `CheckConstraint` naming requirement introduced by
  `Base.metadata`'s naming convention in `db/base.py`.
- `api_client`'s isolation currently works because `httpx.ASGITransport`
  doesn't emit lifespan events, so `create_app()`'s lifespan (which would
  overwrite `app.state.session_factory` with a real engine) never runs.
  Added an assertion guarding that invariant, so a future change that does
  run lifespan (e.g. `asgi_lifespan.LifespanManager`) fails loudly instead
  of silently losing test isolation.

### M0.2 — Foundation Hardening, round 2

Fix wave addressing findings from the M0.1 re-review (spec-compliance,
architecture audit, technical-debt check), before starting M1.

- Fixed the test-isolation gap the M0.1 fixture didn't cover: `db_session`,
  the bot, and the API client all now share one connection-bound,
  rolled-back-transaction `db_session_factory`, via new `bot` and
  `api_client` test fixtures — not just the raw `db_session` fixture.
- Added `admin_only()`, an `app_commands.check`-based enforcement decorator
  for privileged commands (spec §6), and made `HTManagerBot`'s error
  handler distinguish `CheckFailure` (permission denial) from real errors
  instead of logging both as unhandled exceptions. `is_admin()` now also
  verifies guild context (spec §19).
- Moved `get_session` out of `api/app.py` into a new `api/dependencies.py`,
  to avoid a circular import once an M1 router needs both. `create_app()`
  now builds its engine inside `lifespan` for symmetric setup/teardown.
- Added a `naming_convention` to `Base.metadata` and
  `compare_server_default=True` to Alembic's env — must land before M1's
  first migration, since unnamed constraints break `alembic downgrade` and
  migrations can never be edited once applied (spec §5.1).
- Documented transaction-ownership rules in `services/__init__.py` and
  `db/repositories/__init__.py`: repositories and services never commit or
  roll back; the caller owns the unit of work.
- Bumped `pytest-asyncio` to `>=0.26` — the previous `>=0.24` floor didn't
  actually cover `asyncio_default_test_loop_scope`, the same class of bug
  as the still-open `pydantic-settings` floor issue.

### M0.1 — Foundation Hardening

Fix wave addressing findings from the M0 spec-compliance review,
architecture audit, and technical-debt check, before starting M1.

- Wired a DB session path end-to-end: `main.py` creates the engine and
  disposes it on shutdown, `HTManagerBot` carries a `session_factory`, and
  `api/app.py`'s `create_app()` exposes a `get_session` FastAPI dependency
  via `app.state`.
- Fixed `tests/conftest.py`'s `db_session` fixture: tests now run against a
  separate `ht_manager_test` database (auto-migrated once per test session)
  inside a rolled-back transaction, instead of writing directly into the dev
  database with no cleanup.
- Established the command-handler convention for M1: `services/` and
  `db/repositories/` packages, an `is_admin()` permission helper
  (spec §6), and a `CommandTree.on_error` handler so app command errors are
  logged and surfaced instead of silently failing.
- `docker-compose.yml` no longer hardcodes Postgres credentials in the app
  services' `DATABASE_URL` — it's built from `POSTGRES_USER` /
  `POSTGRES_PASSWORD` / `POSTGRES_DB`, configurable via `.env`. Compose
  always deploys and connects to its own `postgres` container by design
  (spec §24's single-VM Compose topology); it does not support pointing at
  an external database.
- `db/models/__init__.py` now documents the model-registration contract,
  enforced by `tests/test_db_models_registration.py`.
- CI now verifies migration reversibility (`upgrade` → `downgrade base` →
  `upgrade`) and runs `alembic check` for model/migration drift.
- `settings.log_level` is now wired into actual logging via
  `ht_manager/logging.py`, used by both the bot and the API.

## [0.1.0] — M0 — Foundation

- Repository scaffold, `pydantic-settings`-based configuration loading,
  Docker Compose Postgres + app Dockerfile, async SQLAlchemy engine/session
  layer, Alembic migration scaffold, Discord bot skeleton with `/ping`,
  FastAPI `/health`, CI (lint, migrations, tests).
