# HT-Manager

Discord bot for HackerTroupe's CTF operations: curating and polling the next
CTF, tracking participation, and syncing/announcing CTFTime results.

Full design: `docs/superpowers/specs/2026-08-04-ht-manager-design.md`.

## Local development

1. Copy `.env.example` to `.env` and fill in real values (Discord bot
   token, guild ID, channel/role IDs, CTFTime team ID). Never commit `.env`.
2. Start Postgres and create the app + test databases (the second command is
   safe to re-run; ignore "already exists" if it prints):
   ```bash
   docker compose up -d --wait postgres
   docker compose exec postgres createdb -U ht_manager ht_manager_test
   ```
3. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
4. Run migrations:
   ```bash
   export DATABASE_URL=postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager
   alembic upgrade head
   ```
5. Run tests and lint. Tests run against a separate `ht_manager_test`
   database (see step 2) and migrate it automatically; override the target
   with `TEST_DATABASE_URL` if needed. Tests that don't touch the database
   (config, the CTFTime client, permissions, formatting) run without Postgres
   at all, so `pytest tests/test_config.py` works on a bare checkout.
   ```bash
   pytest
   ruff check .
   ```
6. Run the bot:
   ```bash
   python -m ht_manager.main
   ```

Or run everything through Compose once `.env` is filled in:

```bash
   docker compose up --build
```

## Deploying

Compose is the deployment unit (spec §24: one small VM). `docker compose up
-d --build` brings up Postgres, runs `alembic upgrade head` as a one-shot
migration job, and only then starts the bot.

Before deploying:

- Fill in `.env` from `.env.example` and **change `POSTGRES_PASSWORD`** —
  the default is a local-development convenience.
- Postgres publishes only to `127.0.0.1`, and the bot/migrate containers run
  as an unprivileged user. Both are deliberate; don't widen them without a
  reason.
- The bot restarts automatically (`restart: unless-stopped`); the migration
  job intentionally does not.

Check on it with `docker compose logs -f ht-manager-bot`. The CTFTime result
sync records its health in the `sync_state` table — `last_success_at` only
advances on a fully clean run, and `last_error` holds the last failure.

## Commands

Admin-only unless noted: `/addctf`, `/editctf`, `/deletectf`, `/nextctf`,
`/resolvepoll`, `/setupctf`, `/addctfmember`, `/removectfmember`,
`/addresult`, `/editresult`, `/resultsync`, `/setcategory`, `/endctf`,
`/archivectf`. Open to everyone: `/ping`, `/ctfmembers`, `/participation`,
`/summary`.

## Project status

M0 through M6 complete: CTF data and CTFTime ingestion, `/nextctf` polling,
event setup (roles/workspace/participation), retention cleanup, result sync,
and end-of-CTF summaries. See `CHANGELOG.md` for details and the spec's
milestone table (§25) for what's next.
