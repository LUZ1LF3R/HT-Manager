# Changelog

All notable changes to HT-Manager are documented here, milestone by
milestone, per `docs/superpowers/specs/2026-08-04-ht-manager-design.md`.

## [Unreleased]

### Fixed — "Cancel Draft" button always failed

`cancel_draft()` deleted the `Poll` row directly, but `poll_options` has no
`ON DELETE CASCADE` and no ORM cascade was configured — every draft has at
least the candidates `/nextctf` created, so the delete always violated the
foreign key and the button silently did nothing. There was no test for
`cancel_draft` at all, which is how this shipped. Fixed by deleting a
draft's options before the poll row; added
`test_cancel_draft_deletes_poll_and_its_options` to cover it.

### Design correction — dedicated per-CTF forum instead of a shared one

Spec §8 originally called for one pre-existing shared Forum channel
(`CTF_FORUM_CHANNEL_ID`) with a post/thread per CTF inside it. That's not
what's wanted: each CTF now gets its own dedicated Forum channel (created
under a `CTF_CATEGORY_ID` category), with a single starting post named
`general` inside it — no shared container.

- `CTF_FORUM_CHANNEL_ID` is gone. Config now has `CTF_CATEGORY_ID` (where a
  CTF's forum is created) and `CTF_ARCHIVE_CATEGORY_ID` (where it's moved
  once the CTF is done).
- `discord_resources.py`: `create_workspace()` is replaced by
  `create_ctf_forum()` (creates the dedicated Forum channel) and
  `create_general_post()` (creates its `general` starting post) — two
  checkpointed steps instead of one, matching the existing role-then-
  workspace incremental-save pattern so a failure between them doesn't
  orphan a forum nothing tracks. New `move_forum_to_category()` relocates a
  forum channel; it logs and returns rather than raising, since it runs
  from a batch job where one failure shouldn't abort the run.
- `ctf_discord_resources` gained `archive_after`/`archived_at` (migration
  `0007`) — a second, independent lifecycle from the existing
  `cleanup_after`/`cleaned_at` retention pair. `/endctf` stamps
  `archive_after` to 4 days out; a new `archive_finished_workspaces` job
  (daily, alongside `cleanup_expired_resources`) moves the forum to
  `CTF_ARCHIVE_CATEGORY_ID` once due and marks it `archived_at`. This is
  deliberately much sooner and separate from the 30–60 day role/thread
  retention cleanup, which still runs unchanged.

### M6.1 — Review fixes and deployment hardening

Findings from a full-codebase review after M6, weighted toward M5/M6.

**The CTFTime result sync never worked.** `services/ctftime.py` called
`/api/v1/events/<id>/results/`, which returns 404 on the live API (verified;
`/api/v1/events/<id>/` returns 200 with the same User-Agent). That 404 was
treated as "standings not published yet", so `_sync_one` returned early for
every CTF on every run — no result was ever recorded, and the run still
stamped `sync_state.last_success_at`. The mocked test asserted the invented
path and an invented `standings` key, so it confirmed the wrong contract
instead of catching it. Replaced with `get_year_results(year)` against the
real `/api/v1/results/<year>/`: keyed by event id, standings under `scores`,
`points` parsed from its string form. `points` is the event score, so it now
lands in `Result.score` (which is what `render_summary` prints) rather than
`rating_points` — spec §12's `Score:` line was previously unreachable for a
synced CTF. Tests now mirror the live payload shape.

Also in the sync:

- One request per *year* instead of per CTF (CTFTime only publishes results
  per year, and one year is ~6 MB).
- `last_success_at` no longer advances when any year or CTF failed; the
  errors are joined into `last_error` instead. A partial run used to report
  as healthy, which made the one health signal misleading.
- Per-CTF failures of any kind are logged and skipped, not just
  `CTFTimeError`; a missing `ctf` row no longer raises mid-run.
- `list_awaiting_result_sync` is bounded — 90 days after `end_at`, and
  excludes hand-corrected results. It previously re-fetched every CTF the
  team had ever run, twice a day, forever.

**`upsert_from_ctftime` no longer overwrites manual corrections.**
`/editresult` marks a result `MANUAL`; the next sync used to overwrite it and
flip the source back to `CTFTIME`, with no audit row — an admin's fix
vanished silently. The sync now leaves `MANUAL` rows alone and reports
`changed=False`, and writes a `result_synced` audit entry when it does act
(every other mutation was already audited).

**`setup_ctf_resources` could orphan a Discord role.** The role and workspace
were created back-to-back and persisted only after both succeeded, so a
workspace failure left a role that nothing recorded — invisible to cleanup,
and duplicated by the next `/setupctf`. Each object is now checkpointed onto
the resource row the moment it exists (`_save_resource`), which is what the
docstring already claimed. `cleanup_after` is still stamped once and never
extended by a retry.

**Tests no longer require Postgres to run at all.**
`_migrated_test_database` was `autouse`, so config, CTFTime-client,
permission, and formatting tests — none of which touch a database — all
failed with connection errors when Postgres was down. It's now opt-in via
`_engine`. That exposed a latent trap: `migrations/env.py` ends in
`asyncio.run()`, which unsets the calling thread's current event loop, and
with the fixture no longer running first that destroyed pytest-asyncio's
session loop and broke every async test after it. The upgrade now runs on a
worker thread. Bot error-handler tests use a new DB-free `offline_bot`
fixture.

Smaller fixes:

- New `/summary <ctf_id>` — renders a CTF's summary without changing its
  status. `render_summary` was only reachable through `finish_ctf`, so a
  `/setcategory` correction made after `/endctf` (the normal order of
  events) updated the database with no way to see the result.
- `/setcategory` now refuses `ARCHIVED`/`CANCELLED` CTFs, matching
  `/editctf`'s existing lock.
- New `bot/formatting.py`: summaries and `/ctfmembers` output are clamped to
  Discord's 2000-character limit (fences included), which Discord otherwise
  rejects outright.
- `/archivectf` no longer replies to Discord from inside an open
  transaction.
- Removed three unreachable `if response is None` branches in the CTFTime
  client — `_get_with_retries` returns or raises, never `None`.

Deployment hardening:

- Containers run as an unprivileged user instead of root.
- `restart: unless-stopped` on the bot and Postgres (not on the one-shot
  migration job).
- Postgres publishes to `127.0.0.1` only — a bare `5432:5432` on the
  deployment VM (spec §24) exposed the database to the internet.
- README documents the deploy path, the commands, and current status
  (it still described M0 and a `/health` endpoint that no longer exists).

### M6 — End Summary

- Added `ctf_category_stats` table (migration `0006`): `CTFCategoryStat`
  (unique per `ctf_id`/`category_name`, `solved`/`total`), populated by
  admins via `/setcategory` — CTFTime's API has no per-category breakdown,
  so this is manual-only, unlike `results`.
- `services/summary.py`: `set_category_stat()` upserts a category row
  (audited); `finish_ctf()` transitions a CTF `ACTIVE` → `FINISHED` via
  `ctfs_service.transition()` (so an invalid-state call fails the same way
  every other transition does) and returns `render_summary()`'s text;
  `render_summary()` composes name/status, placement/score (from
  `results`, if any), a per-category solves breakdown with a total (only
  when stats exist), and a participant count (from `participations`).
- New commands: `/setcategory` (validates `0 <= solved <= total`),
  `/endctf` (finishes a CTF and posts its summary in a code block). Also
  added `/archivectf` (`FINISHED` → `ARCHIVED`) and `/deletectf` — M1 built
  `delete_draft()` but never exposed it as a command; this closes that gap.

### M5 — Results

- Added `results` and `sync_state` tables (migration `0005`): `Result` is
  at most one row per CTF (`/editresult` corrects in place rather than
  inserting a second row, spec §11), sourced `CTFTIME` or `MANUAL`.
  `SyncState` tracks the CTFTime sync's last success/error.
- `services/ctftime.py`: `get_event_results()` reads one event's full
  standings — CTFTime's public API has no "results for team X across all
  events" endpoint, so the sync instead checks each CTF we already track
  (has a `ctftime_event_id`, already ran) against that event's standings
  for our own `CTFTIME_TEAM_ID`.
- `services/results.py`: `add_result`/`edit_result` for `/addresult` and
  `/editresult` (audited), and `upsert_from_ctftime()` — reports
  `changed=False` when placement/team-count/rating already match what's
  stored, which is what stops the 12-hour sync from re-announcing
  identical results on every run (spec §10).
- `jobs/result_sync.py`: runs every 12 hours (also triggerable via
  `/resultsync`), announces genuinely new/changed results to
  `RESULTS_CHANNEL_ID`, and records success/failure in `sync_state`. A
  single CTF's sync failure is logged and skipped rather than aborting
  the run.

### M4 — Cleanup

- `setup_ctf_resources()` now stamps `cleanup_after` (`created_at +
  CTF_RESOURCE_RETENTION_DAYS`) on a `ctf_discord_resources` row the first
  time it's created.
- `jobs/cleanup.py`: a daily APScheduler job that deletes the role and
  archives the workspace thread for any resource past `cleanup_after`,
  then stamps `cleaned_at` — never touches `ctfs`/`participations` (spec
  §14.3, §8). Idempotent: `list_due_for_cleanup` excludes anything already
  `cleaned_at`, and a per-resource Discord failure is logged and skipped
  (retried on the next run) rather than aborting the whole batch.

### M3 — Event Setup

- Added `participations` and `ctf_discord_resources` tables (migration
  `0004`): `Participation` (unique per `ctf_id`/`discord_user_id`, sourced
  `VOTE` or `MANUAL`) and `CTFDiscordResource` (role/forum/thread IDs, never
  deleted — only `cleaned_at` marks Discord-side cleanup, spec §14.3).
- `services/discord_resources.py`: the only module allowed to `import
  discord` for role/forum operations (create/delete role, create workspace
  thread, assign role). Per the spec's §8 implementation note, a shared
  public forum can't restrict one post's visibility independently of the
  others, so the workspace post is a normal visible-to-everyone thread —
  the role exists for pinging/organization, not access control.
- `services/polls.py`: `setup_ctf_resources()` implements the winner-
  resolution sequence (spec §15.2) — create role/workspace, record
  participation for the winning option's voters, assign the role, then
  mark the CTF `ACTIVE`. Each step commits independently with no
  transaction spanning a Discord call, and every step re-checks existing
  state first, so a failure leaves the CTF at its last successful step and
  a retry (`/setupctf`) is a safe no-op on already-completed steps.
  `resolve_tie()` backs `/resolvepoll`: picks a winner among a `TIED`
  poll's leaders, cancels the other leader(s), then the same setup runs.
- `services/participation.py`: manual add/remove (audited) plus an
  idempotent `record_from_vote()` for the automatic path.
- New commands: `/resolvepoll`, `/setupctf`, `/ctfmembers`,
  `/addctfmember`, `/removectfmember`, `/participation`.
- `jobs/poll_close.py` now runs `setup_ctf_resources()` automatically after
  a clean poll win, surfacing failures to `BOT_LOG_CHANNEL_ID` per spec
  §18.1 instead of losing them.

### M2 — `/nextctf`

- Added `polls`, `poll_options`, `poll_votes` tables (migration `0003`) and
  the `Poll`/`PollOption`/`PollVote` models with a `PollStatus` lifecycle
  (`DRAFTING` → `OPEN` → `CLOSED`/`TIED`/`CANCELLED`).
- `services/polls.py`: draft a poll from candidate CTFs, add/remove
  candidates pre-publish, publish (transitions every candidate `DRAFT` →
  `POLLING`), and `finalize()` — tallies per-option voters, a single leader
  wins (`SELECTED`, losers `CANCELLED`), a tie among leaders needs
  `/resolvepoll` (`TIED`, spec §7.3), and zero total votes cancels every
  candidate without creating a workspace. `finalize()` is idempotent: it
  rejects a poll that isn't `OPEN`, so a retried/overlapping run is a no-op.
- `services/ctftime.py`: added `list_upcoming_events()` for the curation
  fetch (spec §7.1 step 3).
- `/nextctf`: blocks if any CTF is already non-terminal (spec §7.1 step 2),
  fetches upcoming CTFTime events, dedups against existing drafts by
  `ctftime_event_id`, and shows a `discord.ui.View` (remove-candidate
  select, Publish/Cancel buttons) before sending a native Discord poll.
- `jobs/poll_close.py`: a 5-minute APScheduler job (wired in
  `bot/client.py`'s `setup_hook`/`close`) that finalizes any `OPEN` poll
  past `closes_at` by reading `PollAnswer.voters()` from the live Discord
  message, then posts the outcome.

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
