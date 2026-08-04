# HT-Manager

Discord bot and API for HackerTroupe's CTF operations: curating and polling
the next CTF, tracking participation, syncing/announcing CTFTime results,
and exposing structured data to hackertroupe.dev.

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
   with `TEST_DATABASE_URL` if needed.
   ```bash
   pytest
   ruff check .
   ```
6. Run the bot:
   ```bash
   python -m ht_manager.main
   ```
7. Run the API:
   ```bash
   uvicorn ht_manager.api.app:create_app --factory --reload
   ```

Or run everything through Compose once `.env` is filled in:

```bash
docker compose up --build
```

## Project status

M0 (Foundation) and M0.1/M0.2 (Foundation Hardening) complete: config
loading, Postgres + Alembic, bot login, `/ping`, `/health`, CI, DB session
wiring, isolated test database. See `CHANGELOG.md` for details and the
spec's milestone table (§25) for what's next.
