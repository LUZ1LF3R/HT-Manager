# HT-Manager — Project Specification

Implementation brief for Claude Code

**Status:** Initial build specification (revised)
**Target:** Discord + CTFTime + website data backend
**Deployment:** Local-first, Dockerized, later Azure for Students
**Site:** https://hackertroupe.dev/

> This revises `HackerTroupe_CTF_Manager_Project_Specification.docx`. Changes from that draft are called out inline as **[REVISED]** or **[NEW]**. Everything else is carried over unchanged because it already held up under review.

## 0. What changed from the original draft

1. **[REVISED] Renamed everywhere.** `CTF Manager` → `HT-Manager`. Repo `ctf-manager/` → `ht-manager/`. Python package `ctf_manager` → `ht_manager`. Docker services → `ht-manager-bot`, `ht-manager-api`. Discord bot display name → `HT-Manager`. Command names (`/nextctf`, etc.) are unchanged — they describe function, not brand.
2. **[REVISED] Single-CTF-at-a-time enforced explicitly.** Confirmed with the team: HackerTroupe never runs two CTFs through the pipeline simultaneously. `/nextctf` now explicitly blocks (rather than silently allowing a second draft) if a CTF is already `POLLING` or `ACTIVE`.
3. **[NEW] `/resolvepoll` command added.** The original spec required an admin to resolve a `TIED` poll (§7.3) but never listed a command for it. Added to the command surface.
4. **[NEW] Continuous-uptime note added to Reliability.** Scheduled jobs (poll close, cleanup, 12-hour CTFTime sync) only fire while the process is running — stated explicitly so this isn't discovered the hard way in production.
5. **[REVISED] Website API section grounded in the real website.** `hackertroupe.dev` is a live static React/Vite SPA on Cloudflare Pages with **no backend today** — `src/data/operations.ts` and `src/data/landingStats.ts` are hardcoded arrays with a client-only localStorage editing layer (edits don't persist for other visitors). HT-Manager's API is the first real dynamic data source this site will have. See §13.
6. **Stack and non-goals unchanged.** Solo maintainer today, rotating team expected within a year — the full stack (Postgres/Alembic/FastAPI/Docker, later Azure) and the "design for handover" principle both hold up; nothing was trimmed.
7. **Member-to-Discord linking is explicitly out of scope.** The website's `Member` type (`src/data/members.ts`) has no Discord user ID field. HT-Manager's API will expose participation by Discord ID / display-name snapshot only; joining that to a website profile is a future website-side concern, not part of this spec.
8. **[NEW] Engineering discipline sections added.** Design Principles, Repository Standards, Service Ownership, Discord abstraction rule, error philosophy, logging levels, and migration rules — all added after a review pass focused on keeping an AI implementer from drifting into monolithic files or ad-hoc error handling. See §2, §5.1, §14.3, §18, §20, §22.1.
9. **[NEW] Single-guild constraint made explicit.** HT-Manager targets exactly one Discord guild (HackerTroupe's). No multi-tenant/multi-server scaffolding is built in — see §6. If a real second-guild need ever appears, `guild_settings.guild_id` is the natural extension point; nothing is reserved for it ahead of time.
10. **[NEW] Developer Workflow and Key Decisions & Rationale sections added.** §30 constrains how Claude Code should move through milestones (one at a time, with lint/test/README/commit/stop between them). §31 records the *why* behind the major architectural calls for future maintainers. See §0.6 for the rotation context that makes this matter.
11. **[NEW] Entity relationships, explicit state transitions, an audit log, API versioning policy, and coding standards added.** §14.1 diagrams table relationships; §15.1 lists every valid lifecycle transition (and states that anything else is rejected); §14.2 adds an `audit_log` table so admin mutations are attributable once more than one person administers the bot; §13 states `/api/v1` won't break in place; §22.2 sets Python-level conventions (type hints, async I/O, no global mutable state, complexity limits).
12. **[REVISED, considered and declined] No in-process event bus.** Discussed adding a domain-event dispatcher between services (PollCreated, WinnerResolved, etc.). Declined: the one real multi-step sequence (winner resolution) has a single caller and a fixed, ordered chain — a dispatcher would add indirection without solving a coupling problem that doesn't exist yet. Kept as direct service calls, with the sequence spelled out explicitly in §15.2 instead. Revisit only if a real fan-out case (multiple independent, unpredictable consumers of the same signal) shows up later.

---

## 1. Purpose

Build a focused Discord bot named **HT-Manager** for HackerTroupe, an unofficial university CTF team. The bot exists to automate CTF selection, participation tracking, temporary event access, results tracking, and structured data that can later be consumed by the HackerTroupe website. It must remain small, predictable, maintainable, and easy for future team members to operate.

## 2. Product Principles

- Do not turn this into a generic all-purpose Discord bot.
- Automate repetitive CTF operations; keep judgment-heavy actions under admin control.
- Discord is an interface, not the permanent source of truth. Persist durable data in the database.
- Temporary Discord roles/forums may be deleted; historical participation and results must never depend on them.
- Prefer simple workflows with explicit admin confirmation over clever but fragile automation.
- Design for handover: clear configuration, migrations, documentation, logs, tests, and Docker deployment. **This matters concretely here** — solo-maintained today, expected to pass to a rotating team within about a year.
- Build locally first. Do not require Azure or any cloud service for development.

### 2.1 Design Principles

- Simplicity over cleverness.
- Explicit state over implicit behavior.
- The database is the source of truth; Discord is a presentation layer over it.
- Every long-running action (poll, sync, cleanup) must be recoverable after a restart.
- All business logic belongs in `services/`, never in Discord command handlers.
- Every service is independently unit-testable without a live Discord connection.
- Keep Discord-specific code as thin as possible — it translates between Discord events and service calls, nothing more.

## 3. Explicit Non-Goals

Do NOT implement the following unless a future specification explicitly adds them:

- Chat/message-based XP.
- First-blood tracking.
- Per-solve contribution tracking.
- Challenge claiming/queue management.
- Practice scheduling.
- Writeup workflow or knowledge base.
- Achievements/badges.
- Discord member profile system.
- Large bot dashboard.
- Recruitment/application system (a separate ticket bot can handle this).
- Automatic creation of many category channels such as #pwn, #web, #rev, etc.
- Heavy analytics inside Discord.
- AI/LLM features.
- Automatic linking of Discord identity to website member profiles (see §0.7).

## 4. High-Level Architecture

```
Cloudflare Pages website (hackertroupe.dev)
        |
        | HTTPS / JSON API (later)
        v
FastAPI / public read-only API
        |
        v
PostgreSQL  <----  Discord HT-Manager bot
                       |
                       +---- CTFTime integration
                       +---- scheduled jobs
                       +---- Discord polls / roles / forum
```

Local development: Docker Compose
Production target: Azure VM via GitHub Student/Azure for Students

## 5. Recommended Stack

| Component | Choice | Notes |
|---|---|---|
| Language | Python 3.13 | Async-first implementation. |
| Discord | discord.py 2.x | Slash commands / app commands and persistent views where needed. |
| Database | PostgreSQL | Durable source of truth. |
| ORM | SQLAlchemy 2.x async | Typed models and explicit transactions. |
| Migrations | Alembic | Never rely on `create_all` for production evolution. |
| HTTP | aiohttp or httpx | Async external requests. |
| Scheduler | APScheduler | 12-hour CTFTime sync and cleanup jobs. |
| API | FastAPI | Website-facing API; can initially be minimal. |
| Packaging | pyproject.toml | Pinned/managed dependencies. |
| Deployment | Docker + Docker Compose | Same topology locally and on Azure. |
| Quality | Ruff + pytest | Formatting/linting and tests. |

### 5.1 Migration Rules

- Every migration must be reversible (`downgrade()` implemented, not a no-op).
- Never edit a migration that has already been applied/merged — always create a new one, even to fix a mistake in the previous one.
- Migrations are the only sanctioned way schema changes reach the database, in every environment including local dev.

## 6. Roles and Permissions

**Single-guild only.** HT-Manager targets exactly one Discord guild — HackerTroupe's. Do not add multi-tenant scaffolding, per-guild command routing beyond what `guild_settings` already provides, or OAuth/external-auth hooks in anticipation of future guilds or teams. `guild_settings.guild_id` is the extension point if this ever changes; nothing else is reserved for it ahead of time.

Define configuration by Discord IDs, never by hard-coded display names.

- `ADMIN_ROLE_IDS`: users allowed to curate CTFs, create/close polls, add manual results, force sync, end/archive CTFs.
- `MEMBER_ROLE_ID`: optional team-member gate for participation commands.
- `RESULTS_CHANNEL_ID`: destination for result announcements.
- `CTF_CATEGORY_ID`: the Discord category a CTF's dedicated Forum channel is created under.
- `CTF_ARCHIVE_CATEGORY_ID`: the Discord category a finished CTF's Forum channel is moved to.
- `BOT_LOG_CHANNEL_ID`: optional private admin channel for operational warnings.

Every privileged command must enforce permissions server-side. Do not rely only on Discord UI visibility.

## 7. Feature A — `/nextctf` Curation and Poll

`/nextctf` is the main workflow. It should fetch relevant upcoming CTFs from CTFTime, stage them for an admin, allow the admin to add/remove entries, and only then publish the poll.

### 7.1 Required workflow

1. Admin runs `/nextctf`.
2. **[REVISED]** Check for an existing CTF in a non-terminal state (`POLLING`, `SELECTED`, or `ACTIVE`). If found, block with a message pointing to `/endctf` or `/archivectf` rather than allowing a second draft — HackerTroupe runs one CTF through the pipeline at a time.
3. Fetch upcoming weekend/relevant CTFs from CTFTime. Do not blindly post everything returned.
4. Persist a draft poll/session in the database.
5. Show the draft list to the admin.
6. Admin can remove CTFs from the draft.
7. Admin can add a custom CTF manually if it is missing from CTFTime.
8. Admin can edit essential custom/draft fields before publishing.
9. Admin explicitly confirms Create Poll.
10. Publish one Discord poll/message containing the approved CTF choices.
11. Store the Discord message/channel IDs and poll metadata so state survives a bot restart.
12. When the poll ends, determine the winning option deterministically.
13. Persist every voter/selected event participation relationship needed by the project.
14. Create the winning CTF's temporary Discord role and workspace.
15. Assign the CTF role to users who voted for the winning option.

### 7.2 CTF draft fields

| Field | Required? | Notes |
|---|---|---|
| name | Yes | Display/event name. |
| year | Yes | Usually derived from start date. |
| ctftime_event_id | No | Null for custom/non-CTFTime events. |
| ctftime_url | No | Event link. |
| official_url | No | Organizer/platform link. |
| start_at | Yes | Store timezone-aware UTC. |
| end_at | Yes | Store timezone-aware UTC. |
| weight | No | CTFTime weight if available. |

### 7.3 Poll edge cases

- **Tie:** do not silently choose at random. Mark poll as `TIED` and require an admin to select the winner via `/resolvepoll` (see §16).
- **Zero votes:** do not create a CTF workspace; notify admin.
- **Deleted poll message:** retain DB state and provide an admin recovery/cancel path.
- **Bot restart:** poll/session state must remain recoverable from database.
- **Duplicate event:** enforce uniqueness where reasonable (e.g., CTFTime event ID) and warn the admin.

## 8. Feature B — Temporary CTF Role and Workspace

After a poll winner is finalized, create a temporary role named using the event, e.g. `L3akCTF 2026`. The role is for access control only; it is not the historical participation record.

- Assign the role to users who voted for the winning CTF.
- **[REVISED]** Create a dedicated Forum channel for the CTF, named after the event, under the `CTF_CATEGORY_ID` category — not a post/thread inside a shared forum.
- Create a single starting post named `general` inside that forum channel.
- Only the relevant CTF role (plus administrators/moderators/bot) should be able to access the CTF workspace where Discord permissions allow this design.
- Do not create separate #pwn/#web/#rev/#crypto/etc. channels.
- Store role ID and forum/post IDs in the database.
- **[REVISED]** A configurable number of days after `/endctf` (default 4), move the CTF's Forum channel to the `CTF_ARCHIVE_CATEGORY_ID` category. This is independent of, and much sooner than, role/thread retention cleanup.
- After a configurable retention period (default 60 days; allow 30–60 via configuration), remove/delete the temporary role and archive/lock the workspace's `general` post as appropriate.
- Cleanup must never delete participation/history records.

**Implementation note:** Discord Forum permission semantics should be validated against the actual server layout. If per-post visibility cannot be restricted independently in the chosen forum design, document the limitation and use the simplest permission-safe alternative rather than inventing a complex channel tree.

## 9. Feature C — Participation Tracking

Participation is the only XP-like concept. Do not create arbitrary points. The core metric is how many CTFs a member participated in.

- Record participation by Discord user ID + CTF ID.
- A member should count at most once per CTF.
- Initial participation can be inferred from voting for the winning poll option.
- Admins need a way to correct participation manually because voters may drop out or members may join after the poll.
- Historical participation remains after Discord roles are deleted.
- Expose aggregate participation data through the future website API.
- Suggested commands: `/participation`, `/ctfmembers`, `/addctfmember`, `/removectfmember` (names may be adjusted for consistency).

## 10. Feature D — CTFTime Result Tracker

Check HackerTroupe's CTFTime team results on a 12-hour schedule. The exact CTFTime team identifier must be configuration, not hard-coded.

- Run every 12 hours, not hourly.
- Fetch/derive the latest team result/placement data available from CTFTime.
- Compare against persisted known results.
- Only announce genuinely new or changed results.
- Post result announcements to the configured #results channel.
- Do not spam identical results on every scheduled run.
- Record raw/source identifiers where available so duplicate detection is reliable.
- Use timeouts, retries with backoff, and clear logging for external failures.
- Respect CTFTime's available interfaces and avoid aggressive scraping.
- Because CTFTime interfaces/HTML can change, isolate CTFTime parsing/client code behind a service abstraction and cover parsing with fixtures/tests.

## 11. Feature E — Manual Results

Not every result will appear on CTFTime promptly. Admins must be able to create or correct results manually.

- Provide `/addresult` for admins.
- Allow event, placement, total teams (if known), score (optional), rating/rating delta (optional), result/source URL (optional), and notes (optional).
- Manual results use the same database model and announcement formatting as synchronized results.
- Mark result source as `MANUAL` or `CTFTIME`.
- Provide a safe edit/correction command rather than requiring direct database edits.
- Prevent accidental duplicate announcements.

## 12. Feature F — End-of-CTF Summary

Support automatic or admin-triggered final summaries. Automatic generation is allowed only when the required data is available reliably; otherwise prompt/admin commands should supply missing values.

```
L3akCTF 2026 — Finished
Placement: 47 / 1000
Score: 8214
Solves
  Web       8/8
  Pwn       5/9
  Rev       6/8
  Crypto    3/5
  Misc      7/7
  Forensics 4/6
Total solved: 33/43
Participants: 12
```

- Category format must be `solved/total`, e.g. `Web 8/8`.
- Category names are not fixed; support arbitrary categories.
- Store category summary as structured data, not only rendered text.
- Do not invent category totals if the source does not expose them.
- Allow `/endctf` or equivalent admin command to enter/correct summary data.
- If final placement is known, connect the summary to the result record.

## 13. Feature G — Website Data/API

The existing website (`hackertroupe.dev`) is a static React/Vite SPA deployed from GitHub through Cloudflare Pages, and **has no backend today**. Content that will eventually be fed by this API is currently hardcoded and manually maintained:

- `src/data/operations.ts` — a manually-edited `Operation[]` array (fields: `category` (`CTF`/`Hackathon`/`Research`), `name`, `date`, `outcome`, `organizer`, `description`, `participants`, `year`) with a client-only localStorage editing layer that does **not** persist edits for other visitors. This is the closest existing analogue to `/api/v1/results` / `/api/v1/ctfs`.
- `src/data/landingStats.ts` — a hardcoded `ctfsPlayed` counter (plus hackathons/projects/research logs, out of scope here) that maps to `/api/v1/stats`.
- `src/data/members.ts` — team member profiles keyed by an internal `id`/`alias`, with no Discord user ID. Per §0.7, joining Discord participation data to these profiles is out of scope for this spec; the API exposes participation by Discord display-name snapshot only.

Keep the website on Cloudflare Pages. The bot/backend provides structured data the website can consume when the team is ready to wire it up — this spec does not require the website itself to be modified.

Initial public read-only endpoints should be deliberately small:

```
GET /health
GET /api/v1/ctfs
GET /api/v1/ctfs/{id}
GET /api/v1/results
GET /api/v1/participation
GET /api/v1/stats
```

- Do not expose Discord tokens, internal IDs unnecessarily, admin notes, or secrets.
- Use stable JSON schemas and version the API (`/api/v1`).
- **Versioning policy:** `/api/v1` is stable once shipped — no breaking changes to existing v1 fields/routes. A breaking change (removing/renaming a field, changing a type, removing a route) requires a new `/api/v2`, released alongside v1 rather than in place of it. Additive changes (new optional fields, new routes) are fine within v1.
- Enable CORS only for the HackerTroupe website origin(s) (`hackertroupe.dev`, likely served from `api.hackertroupe.dev`) plus local development origins.
- Public stats can include total CTFs, total recorded participations, recent results, season counts, and participation leaderboard/counts.
- The website, not the Discord bot, is the intended place for richer analytics/visualization.

## 14. Suggested Database Model

| Table | Core fields / purpose |
|---|---|
| guild_settings | guild_id, admin role IDs/config references, channel IDs, retention_days, ctftime_team_id. |
| members | discord_user_id, display snapshot, first_seen_at, active flag. Do not make display name the key. |
| ctfs | id, name, year, ctftime_event_id nullable, URLs, start_at, end_at, status, created_at. |
| polls | id, guild_id, discord_message_id, channel_id, status, closes_at, winning_ctf_id nullable. |
| poll_options | poll_id, ctf_id, option index/identifier. |
| poll_votes | poll_id, ctf_id, discord_user_id, recorded_at. |
| participations | ctf_id, discord_user_id, source, joined_at; unique(ctf_id, discord_user_id). |
| ctf_discord_resources | ctf_id, role_id, forum/thread/post IDs, created_at, cleanup_after, cleaned_at, archive_after, archived_at. |
| results | ctf_id, source, placement, total_teams, score, rating fields, source_url, announced_at, timestamps. |
| ctf_category_stats | ctf_id, category_name, solved, total. |
| sync_state | integration key, cursor/hash/last_success/last_error as needed. |
| audit_log | id, discord_user_id (actor), action, target_table, target_id, before (JSON, nullable), after (JSON, nullable), created_at. |

Use proper foreign keys, uniqueness constraints, indexes on external IDs and Discord IDs, UTC timestamps, and migrations.

### 14.1 Entity Relationships

```
ctfs
 ├── poll_options ── polls ── poll_votes
 ├── participations
 ├── results ── ctf_category_stats
 └── ctf_discord_resources

members (by discord_user_id)
 ├── participations
 ├── poll_votes
 └── audit_log (as actor)

guild_settings ── (config only, not FK-referenced by the above)
sync_state ── (independent, tracks external integration cursors)
```

`polls` and `ctfs` are 1:1 per pipeline run (§15) — a `ctf` has at most one non-terminal `poll` at a time, enforced at the application level per §7.1, not by a DB constraint alone.

### 14.2 Audit Log

- Every admin command that mutates state (`/addctf`, `/editctf`, `/deletectf`, `/resolvepoll`, `/addctfmember`, `/removectfmember`, `/addresult`, `/editresult`, `/endctf`, `/archivectf`) writes one `audit_log` row: who, what action, what changed (before/after snapshot of the affected fields), when.
- This is a direct write from the command/service that performs the mutation — no event bus or dispatcher (§15.2 explains why one isn't used here).
- `audit_log` rows are never deleted or edited, including by the retention/cleanup job in §8.
- This becomes load-bearing once the team is no longer solo (§0.6) — it's the record of who did what when multiple admins share the bot.

### 14.3 Data Retention Rules

- Never hard-delete a record that has recorded activity attached to it (a CTF with votes/participation/results, a poll that has opened, a finalized result). Retire it through its `status` field (`CANCELLED`, `ARCHIVED`) instead.
- `DRAFT`-stage records with no participation or results yet are the one exception — `/deletectf` may hard-delete these, since there is no history to protect.
- Discord-side resources (roles, forum posts) are disposable and may be deleted per the retention job in §8. The database rows recording that they *existed* (`ctf_discord_resources`) are not deleted, only marked cleaned (`cleaned_at`).

## 15. CTF Lifecycle / State Machine

```
DRAFT -> POLLING -> SELECTED -> ACTIVE -> FINISHED -> ARCHIVED
```

Possible exceptional states: `CANCELLED`, `TIED` (poll requires admin resolution via `/resolvepoll`).

**[REVISED]** Only one CTF may occupy a non-terminal state (`POLLING`, `SELECTED`, `ACTIVE`, or `TIED`) at a time per guild. `/nextctf` enforces this (§7.1).

Do not infer lifecycle only from Discord objects. Store status explicitly. Scheduled jobs should be idempotent and safe to run more than once.

### 15.1 Valid Transitions

| From | To | Trigger |
|---|---|---|
| `DRAFT` | `POLLING` | Admin confirms "Create Poll" in `/nextctf` (§7.1 step 9). |
| `DRAFT` | `CANCELLED` | `/deletectf` on a draft. |
| `POLLING` | `SELECTED` | Poll closes with a clear winner. |
| `POLLING` | `TIED` | Poll closes with a tie (§7.3). |
| `POLLING` | `CANCELLED` | Admin cancels via the recovery path (§7.3, deleted poll message). |
| `TIED` | `SELECTED` | Admin resolves via `/resolvepoll`. |
| `SELECTED` | `ACTIVE` | Role + workspace creation completes (§15.2). |
| `ACTIVE` | `FINISHED` | `/endctf`. |
| `FINISHED` | `ARCHIVED` | Retention cleanup job or `/archivectf`. |
| any non-terminal state | `CANCELLED` | Admin cancellation, exceptional cases only. |

Any transition not listed above is invalid and must be rejected by the service layer (e.g. `ACTIVE → DRAFT`, `ARCHIVED → ACTIVE`, `FINISHED → POLLING`). This is enforced in `services/ctfs.py`, not left to callers to get right.

### 15.2 Winner Resolution Sequence

Triggered once by either a clean poll win or `/resolvepoll` on a `TIED` poll. Runs as an ordered sequence, not through an event bus or dispatcher — the chain is fixed, has exactly one caller, and each step's failure handling depends on knowing what came before it (§2.1, §22.1):

1. `polls.py` marks the CTF `SELECTED` and records the winning option.
2. `polls.py` calls `discord_resources.py` to create the temporary role and forum workspace.
3. `polls.py` calls `participation.py` to record participation for each voter of the winning option.
4. `polls.py` calls `discord_resources.py` to assign the new role to those same voters.
5. `polls.py` marks the CTF `ACTIVE`.

If any step fails, log per §18.1, leave the CTF in its last successfully-reached state (do not advance to `ACTIVE`), and surface the failure to `BOT_LOG_CHANNEL_ID` so an admin can retry via `/setupctf`. Steps 2–4 should be individually idempotent so a retry doesn't create duplicate roles/workspaces or double-count participation.

## 16. Commands — Target Surface

| Command | Who | Purpose |
|---|---|---|
| `/nextctf` | Admin | Fetch and curate upcoming CTFs; start poll workflow. Blocks if a CTF is already in a non-terminal state. |
| `/addctf` | Admin | Add custom CTF to database/draft. |
| `/editctf` | Admin | Correct CTF metadata. |
| `/deletectf` | Admin | Delete/cancel appropriate draft record; protect historical data. |
| `/setupctf` | Admin | Manually/repair creation of role + workspace. |
| `/resolvepoll` | Admin | **[NEW]** Manually select the winning option for a `TIED` poll; triggers the same winner-finalization path (role + workspace + participation) as a clean win. |
| `/ctfmembers` | Member/Admin | Show participants for an event. |
| `/addctfmember` | Admin | Manual participation correction. |
| `/removectfmember` | Admin | Manual participation correction. |
| `/addresult` | Admin | Create manual result. |
| `/editresult` | Admin | Correct result. |
| `/resultsync` | Admin | Run CTFTime result sync immediately. |
| `/endctf` | Admin | Finalize event and category solve summary. |
| `/archivectf` | Admin | Archive/cleanup an event when needed. |
| `/participation` | Member/Admin | Simple participation counts/list; no XP. |
| `/ping` | Everyone | Health/latency check. |

Do not implement every command before the core workflow works. Command names may be normalized, but `/nextctf` is specifically required.

## 17. Configuration and Secrets

```
# .env.example — never commit real values
DISCORD_TOKEN=
DISCORD_GUILD_ID=
DATABASE_URL=postgresql+asyncpg://...
CTFTIME_TEAM_ID=
RESULTS_CHANNEL_ID=
CTF_CATEGORY_ID=
CTF_ARCHIVE_CATEGORY_ID=
ADMIN_ROLE_IDS=
MEMBER_ROLE_ID=
CTF_RESOURCE_RETENTION_DAYS=60
PUBLIC_API_ORIGINS=https://hackertroupe.dev
LOG_LEVEL=INFO
```

- Commit `.env.example`, never `.env`.
- Validate required configuration at startup and fail with actionable messages.
- Do not log the Discord token, database password, cookies, authorization headers, or full secrets.

## 18. Reliability Requirements

- All scheduled jobs must be idempotent.
- Use database transactions around multi-step state changes.
- External calls must have timeouts.
- Retry transient failures with bounded exponential backoff.
- A failed CTFTime sync must not crash the bot.
- A Discord permission failure should be logged and surfaced to admins with enough context to repair it.
- Bot restart must not lose polls, CTF lifecycle, participation, cleanup schedule, or result sync state.
- **[NEW]** Poll closing, cleanup jobs, and the 12-hour CTFTime sync only fire while the bot process is running continuously. This has two consequences: (1) meaningful local testing of poll-close/cleanup timing requires the bot to stay running, not just spin up for a session; (2) production on the Azure VM must run continuously, or scheduled jobs silently slip and need manual reconciliation on restart.
- Use UTC internally; render Discord timestamps/localized times for users.
- Gracefully shut down DB/HTTP sessions.

### 18.1 Error Philosophy

- Never silently swallow an error. At minimum, log it with context (§20).
- If an error affects something an admin needs to act on (a failed sync, a permission error creating a role), surface it to `BOT_LOG_CHANNEL_ID`, not just the log file.
- One failed external call (Discord API, CTFTime) must never crash the bot process. Catch at the boundary, log, retry per §18's backoff rule, and degrade gracefully (e.g., skip that job run, don't lose state).

## 19. Security Requirements

- Least-privilege Discord bot permissions. Do not grant Administrator unless absolutely unavoidable.
- Use role/channel IDs from configuration and verify guild context.
- Admin-only commands require explicit authorization checks.
- Never accept arbitrary SQL, shell commands, file paths, or URLs that are executed/fetched without validation.
- Parameterize all database operations through the ORM.
- Rate-limit or permission-gate expensive/admin actions.
- Public FastAPI endpoints are read-only in the initial version.
- If write APIs are added later, use real authentication; do not rely on obscurity.
- Pin dependencies and keep them updateable.

## 20. Logging and Observability

- Structured logs with event/action context: guild_id, ctf_id, poll_id, job name; avoid sensitive values.
- Log startup configuration summary without secrets.
- Log CTFTime sync start/success/failure and number of changes.
- Log role/workspace creation and cleanup.
- Log admin mutations such as manual result changes.
- Expose `/health` for the API and `/ping` for Discord.

**Level usage:**

| Level | When |
|---|---|
| `DEBUG` | Disabled by default; verbose internals for local troubleshooting only. |
| `INFO` | Normal operation — commands run, jobs completed, resources created/cleaned. |
| `WARNING` | Recoverable problems — a retry succeeded, a Discord permission was missing but the bot continued. |
| `ERROR` | Unexpected failures that needed intervention or left something in a degraded state. |

## 21. Testing Requirements

- Unit tests for lifecycle/state transitions.
- Unit tests for poll winner logic including tie and zero-vote cases.
- Unit tests for participation uniqueness.
- CTFTime parser/client tests using saved fixtures; tests must not depend on live CTFTime.
- Tests for result deduplication.
- Tests for end-summary totals and arbitrary categories.
- API schema/endpoint tests.
- Mock Discord API boundaries; do not require a live server for the main test suite.
- A feature is not complete if its only validation is manual testing in the production Discord server.

## 22. Development and Repository Layout

```
ht-manager/
├── src/
│   └── ht_manager/
│       ├── bot/
│       │   ├── commands/
│       │   ├── views/
│       │   └── events/
│       ├── services/
│       │   ├── ctftime.py
│       │   ├── ctfs.py
│       │   ├── polls.py
│       │   ├── participation.py
│       │   ├── discord_resources.py
│       │   └── results.py
│       ├── jobs/
│       ├── api/
│       ├── db/
│       │   ├── models/
│       │   └── repositories/
│       ├── schemas/
│       ├── config.py
│       └── main.py
├── migrations/
├── tests/
│   └── fixtures/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── README.md
└── .github/workflows/ci.yml
```

### 22.1 Repository Standards

- No god classes/modules. Each service in `services/` owns one responsibility (below) and nothing else.
- File size: 500 lines preferred, 1000 lines is a hard ceiling. Split a service into a subpackage before it crosses that line rather than letting it keep growing.
- Business logic never calls `discord.py` directly. All Discord API interaction goes through `services/discord_resources.py`, which owns role creation/deletion, forum post creation/archival, and announcement posting. Other services depend on its interface, not on `discord.py` types. If `discord_resources.py` itself outgrows the 500-line guideline, split it into a subpackage (e.g. `discord_resources/roles.py`, `discord_resources/forum.py`) at that point — not preemptively.

**Service ownership:**

| Service | Owns | Owns nothing else |
|---|---|---|
| `ctfs.py` | CTF metadata CRUD, draft fields, uniqueness checks (§7.2, `/addctf`, `/editctf`, `/deletectf`). | Not poll lifecycle, not participation. |
| `ctftime.py` | CTFTime HTTP client and response parsing only, behind a stable interface. Isolated so CTFTime instability can't leak into the rest of the codebase (§10). | Not scheduling, not result persistence. |
| `polls.py` | Poll creation, poll lifecycle, winner selection, tie detection, `/resolvepoll`. | Not role/workspace creation — it calls `discord_resources.py` and `participation.py` once a winner is known. |
| `participation.py` | Recording/correcting participation rows, per-CTF uniqueness. | Not how participation was inferred (that's `polls.py`'s job to call into it). |
| `discord_resources.py` | All direct `discord.py` calls: role create/assign/delete, forum post create/archive, announcement posting. | Not business rules about *when* to do these things. |
| `results.py` | Result persistence, CTFTime sync comparison/deduplication, `/addresult`, `/editresult`, category summary storage. | Not the CTFTime HTTP client itself (delegates to `ctftime.py`). |

This ownership split is what keeps `/nextctf`'s command handler thin: it calls into `ctfs.py`, `ctftime.py`, and `polls.py` in sequence and contains no business logic of its own.

### 22.2 Coding Standards (Python)

- Type hints on all function signatures; no bare `Any` without a comment justifying it.
- Async for all I/O — Discord calls, HTTP calls, database queries. No blocking calls in async code paths.
- Pydantic models for API request/response schemas; SQLAlchemy models for persistence. Don't pass raw dicts across service boundaries.
- No global mutable state. Configuration and DB sessions are passed in or injected, not module-level singletons mutated at runtime.
- Keep cyclomatic complexity low — enforce via Ruff's `C901` (`max-complexity`), not just convention.
- Public functions get a one-line docstring stating intent if the name doesn't already make it obvious; skip docstrings that just restate the function name.
- Private/internal helpers are prefixed `_` and not exported from their module.

## 23. Local Development First

Claude Code should make local development the first-class workflow.

```
docker compose up -d postgres
# run migrations
# start bot/API in development mode
# run tests and lint locally
```

- Do not provision Azure as part of the application code.
- Do not couple the code to Azure-specific databases or queues.
- Production deployment should be a later, thin layer over the same Dockerized application.

## 24. Production Target (Later)

The user currently has Azure for Students with credit available. Production will likely be a small Ubuntu Azure VM. The website remains on Cloudflare Pages. The VM can run Docker Compose with the bot, PostgreSQL, API, and optionally Caddy/Nginx for HTTPS.

- Keep resource usage low.
- Do not select expensive managed Azure services by default.
- Back up PostgreSQL before upgrades/migrations.
- Use a subdomain such as `api.hackertroupe.dev` through Cloudflare when the API is deployed.

## 25. Implementation Order

| Milestone | Deliverable |
|---|---|
| M0 — Foundation | Repository, config, Docker Postgres, SQLAlchemy/Alembic, bot login, `/ping`, tests/CI. |
| M1 — CTF Data | CTF models, CTFTime client, `/addctf`, `/editctf`, draft lifecycle. |
| M2 — `/nextctf` | Fetch, curate, add/remove, publish poll, persist state, tie/zero-vote handling, single-track enforcement. |
| M3 — Event Setup | Winner finalization, temporary role, forum workspace, participation records, `/resolvepoll`. |
| M4 — Cleanup | 30–60 day role/workspace cleanup, idempotent recovery. |
| M5 — Results | 12-hour CTFTime sync, #results announcements, `/addresult`, `/editresult`, deduplication. |
| M6 — End Summary | Category solved/total data and `/endctf`. |
| M7 — Website API | Read-only FastAPI v1 endpoints and CORS for `hackertroupe.dev`. |
| M8 — Production | Docker hardening, backup notes, Azure VM deployment documentation. |

## 26. Definition of Done

- An admin can run `/nextctf`, curate the CTF list, publish a poll, and resolve a winner (including manually via `/resolvepoll` on a tie).
- Winning voters receive the temporary CTF role and participation is persisted.
- A minimal CTF forum workspace is created without channel spam.
- Temporary Discord resources can be cleaned after the configured retention period without losing history.
- CTFTime results are checked every 12 hours and only new/changed results are announced.
- Admins can add/correct results manually.
- An event can be finalized with category data in `solved/total` format.
- Participation and result data are queryable for the website through a small read-only API.
- Restarting the bot does not destroy operational state.
- Every admin mutation (add/edit/delete CTF, resolve poll, correct participation, add/edit result, end/archive CTF) produces an `audit_log` row.
- Migrations, tests, linting, `.env.example`, Docker files, and a usable README are included.

## 27. Instructions to Claude Code

- Treat this document as the product contract. Before writing large amounts of code, inspect the repository and produce a short implementation plan mapped to the milestones above. Then implement incrementally. Do not add features merely because they are common in Discord bots.
- Ask only when a missing value materially blocks implementation (e.g., actual guild/channel/role IDs or CTFTime team ID). Otherwise use environment variables/placeholders.
- Do not silently expand scope.
- Do not replace PostgreSQL with SQLite for the final architecture; tests may use an isolated test database strategy if appropriate.
- Do not hard-code secrets or server-specific IDs.
- Do not implement XP, first bloods, achievements, challenge queues, practice scheduling, writeup workflows, or bot profiles.
- Do not implement automatic Discord-to-website-profile linking (§0.7) — participation data is exposed by Discord display-name snapshot only.
- Keep Discord-specific code thin; put business rules in services so they are testable.
- Prefer explicit state machines and database constraints over implicit behavior.
- When CTFTime behavior is uncertain or unstable, isolate it, document assumptions, and make manual admin fallback possible.
- Do not fabricate external API capabilities. If a platform does not expose solve/category data, require admin input for that data.
- At the end of each milestone: run tests, lint, migrations/checks, and update README.

## 28. Open Configuration Values to Obtain

These are intentionally not invented in this specification:

- Discord application/bot token.
- Discord guild/server ID.
- Admin role ID(s).
- Member role ID if used.
- #results channel ID.
- Forum channel/container ID and exact desired Discord permission model.
- HackerTroupe CTFTime team ID.
- Preferred role/workspace retention period (default implementation: 60 days).

~~Actual HackerTroupe website origin/domain for CORS/API DNS~~ — resolved: `hackertroupe.dev`, API likely on `api.hackertroupe.dev`.

## 29. Final Scope Summary

HT-Manager should do a small number of things extremely well: help admins choose the next CTF, poll members, grant temporary event access, permanently record participation, track/post results, finalize useful CTF summaries, and expose clean structured data for the HackerTroupe website. Everything else is out of scope until explicitly requested.

## 30. Developer Workflow

This governs how Claude Code (or any implementer) moves through the milestones in §25. It exists to stop a single session from trying to build the whole application at once, which produces large, hard-to-review, hard-to-test changes.

For each milestone:

1. Read this specification (or the relevant sections) and the current state of the repository — do not assume prior context is still accurate.
2. Inspect what already exists before writing anything new.
3. State the implementation plan for **this milestone only** before writing code.
4. Implement that one milestone.
5. Run Ruff and pytest (mypy too, if/when it's adopted). Fix anything they surface.
6. Update the README if the milestone changed how the project is run, configured, or tested.
7. Commit.
8. Stop. Do not continue to the next milestone unless explicitly asked to.

This applies within a milestone too: if a milestone is large (e.g. M2 — `/nextctf`), it's fine to check in with the user between major sub-steps rather than delivering the entire milestone unreviewed.

## 31. Key Decisions & Rationale

Short version of *why*, for whoever picks this project up later.

- **PostgreSQL over SQLite.** The bot, the scheduled jobs, and the API all write/read concurrently. Docker Compose makes Postgres free during local dev, so there's no simplicity gained by using SQLite and having to migrate off it later — see §27's explicit prohibition on this.
- **One active CTF at a time (§7.1, §15).** Matches how HackerTroupe actually operates and removes an entire category of concurrency bugs (which CTF does this vote/command apply to?) for no lost functionality.
- **Discord as a presentation layer, database as source of truth (§2.1).** Roles and forum posts are temporary and admin-deletable by nature of Discord; the historical record (who played what, what the result was) must survive that. This is why `ctf_discord_resources` tracks IDs but participation/results tables never reference Discord objects as their primary key.
- **Local-first, Azure last (§23, §24, M8).** Cloud infrastructure is the part most likely to change (credits run out, hosting preferences change); the application shouldn't be coupled to it. Docker Compose gives the same topology locally and in production, so "deploy to Azure" is a thin final layer, not a rewrite.
- **Single-guild only (§6, §0.9).** HackerTroupe is one team on one server. Multi-guild support would touch nearly every table's schema for a need that doesn't exist yet; `guild_settings.guild_id` is enough of a seam to extend from later if it ever does.
- **discord.py wrapped behind `discord_resources.py` (§22.1).** Keeps every other service testable without a live Discord connection, and keeps the blast radius of a discord.py version upgrade contained to one file.
