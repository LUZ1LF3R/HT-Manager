# HT-Manager M0 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the HT-Manager repository skeleton — config loading, Docker Postgres, async SQLAlchemy + Alembic wiring, a Discord bot that logs in and responds to `/ping`, a FastAPI `/health` endpoint, CI, and a working local dev README — so M1 (CTF data models) has a working foundation to build on.

**Architecture:** A single `ht_manager` Python package with three thin entrypoints (Discord bot, FastAPI app, Alembic migrations) sharing one config module and one async DB session layer. No domain logic yet — that starts in M1. Everything runs locally via Docker Compose against a real Postgres container; CI runs the same test suite against a Postgres service container.

**Tech Stack:** Python 3.13, discord.py 2.x, SQLAlchemy 2.x (async) + asyncpg, Alembic, FastAPI + uvicorn, pydantic-settings, pytest + pytest-asyncio, Ruff, Docker Compose, GitHub Actions.

## Global Constraints

Copied verbatim from `docs/superpowers/specs/2026-08-04-ht-manager-design.md` — every task below implicitly includes these:

- Python 3.13, async-first implementation (spec §5).
- discord.py 2.x for the Discord bot (spec §5).
- PostgreSQL is the durable source of truth; never substitute SQLite, including in the final architecture (spec §5, §27).
- SQLAlchemy 2.x async ORM; Alembic for migrations, never `create_all` (spec §5).
- Every migration must be reversible; never edit an already-applied migration — always create a new one (spec §5.1).
- FastAPI for the public API; pyproject.toml for packaging; Docker + Docker Compose for deployment, same topology locally and in production; Ruff + pytest for quality (spec §5).
- Single-guild only. No multi-tenant/multi-server scaffolding (spec §6).
- Never commit `.env`; never log the Discord token, DB password, or other secrets (spec §17, §19).
- Validate required configuration at startup and fail with an actionable error message (spec §17).
- Type hints on every function signature; no bare `Any` without a justifying comment (spec §22.2).
- Async for all I/O; no blocking calls in async code paths (spec §22.2).
- No global mutable state — config and DB sessions are passed in, not module-level singletons mutated at runtime (spec §22.2).
- Cyclomatic complexity enforced via Ruff's `C901`, `max-complexity = 10` (spec §22.2).
- File size: 500 lines preferred, 1000 lines is a hard ceiling (spec §22.1).
- Keep Discord-specific code thin — command handlers translate events to calls, no business logic in them (spec §2.1, §22.1).
- Least-privilege Discord bot permissions; never grant Administrator (spec §19).

---

## File Structure

```
ht-manager/
├── src/
│   └── ht_manager/
│       ├── __init__.py
│       ├── config.py                  # Settings, SettingsError, get_settings()
│       ├── main.py                    # bot entrypoint: main()
│       ├── bot/
│       │   ├── __init__.py
│       │   ├── client.py              # HTManagerBot, build_bot()
│       │   └── commands/
│       │       ├── __init__.py
│       │       └── ping.py            # ping_reply(), register_ping_command()
│       ├── api/
│       │   ├── __init__.py
│       │   └── app.py                 # create_app(), app
│       └── db/
│           ├── __init__.py
│           ├── base.py                # Base (declarative base)
│           └── session.py             # create_engine(), create_session_factory()
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_baseline.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # db_session fixture
│   ├── test_config.py
│   ├── test_db_session.py
│   ├── test_ping.py
│   └── test_api_health.py
├── alembic.ini
├── Dockerfile
├── .dockerignore
├── docker-compose.yml
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
└── .github/workflows/ci.yml
```

Each file has one job: `config.py` only loads/validates settings, `db/session.py` only knows how to build an engine/session from a URL (no dependency on `Settings`, so it's testable standalone), `bot/commands/ping.py` separates the pure reply-formatting logic from the discord.py glue, `api/app.py` is the FastAPI factory. No domain tables or business services yet — those start in M1.

---

### Task 1: Repository scaffold and tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/ht_manager/__init__.py`, `src/ht_manager/bot/__init__.py`, `src/ht_manager/bot/commands/__init__.py`, `src/ht_manager/api/__init__.py`, `src/ht_manager/db/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: an installable `ht_manager` package (`pip install -e .[dev]`) with Ruff and pytest configured. Later tasks assume these are already runnable.

- [ ] **Step 1: Initialize the git repository**

```bash
git init
```

- [ ] **Step 2: Create the package and test directory skeleton**

```bash
mkdir -p src/ht_manager/bot/commands src/ht_manager/api src/ht_manager/db tests
touch src/ht_manager/__init__.py
touch src/ht_manager/bot/__init__.py
touch src/ht_manager/bot/commands/__init__.py
touch src/ht_manager/api/__init__.py
touch src/ht_manager/db/__init__.py
touch tests/__init__.py
```

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "ht-manager"
version = "0.1.0"
description = "HackerTroupe CTF Discord bot and API"
requires-python = ">=3.13"
dependencies = [
    "discord.py>=2.4,<3",
    "sqlalchemy[asyncio]>=2.0,<3",
    "asyncpg>=0.29,<1",
    "alembic>=1.13,<2",
    "httpx>=0.27,<1",
    "apscheduler>=3.10,<4",
    "fastapi>=0.115,<1",
    "uvicorn[standard]>=0.30,<1",
    "pydantic-settings>=2.4,<3",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.6,<1",
    "pytest>=8,<9",
    "pytest-asyncio>=0.24,<1",
]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "C901"]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
.ruff_cache/
dist/
*.egg-info/
```

- [ ] **Step 5: Install the project in editable mode with dev dependencies**

```bash
pip install -e ".[dev]"
```

- [ ] **Step 6: Verify tooling runs cleanly on the empty scaffold**

```bash
ruff check .
pytest
```

Expected: `ruff check .` reports no errors; `pytest` collects 0 tests and exits 0 (no test files exist yet).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore src tests
git commit -m "chore: scaffold ht-manager package and tooling"
```

---

### Task 2: Configuration loading

**Files:**
- Create: `src/ht_manager/config.py`
- Create: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing beyond the package scaffold from Task 1.
- Produces: `Settings` (pydantic `BaseSettings` subclass), `SettingsError` (exception), `get_settings() -> Settings`. Fields on `Settings`: `discord_token: str`, `discord_guild_id: int`, `database_url: str`, `ctftime_team_id: str`, `results_channel_id: int`, `ctf_forum_channel_id: int`, `admin_role_ids: list[int]`, `member_role_id: int | None`, `bot_log_channel_id: int | None`, `ctf_resource_retention_days: int` (default 60), `public_api_origins: list[str]` (default `[]`), `log_level: str` (default `"INFO"`). Later tasks (bot, main) call `get_settings()` to obtain a validated `Settings` instance.

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
import pytest

from ht_manager.config import SettingsError, get_settings

REQUIRED_ENV = {
    "DISCORD_TOKEN": "fake-token",
    "DISCORD_GUILD_ID": "123456789",
    "DATABASE_URL": "postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager",
    "CTFTIME_TEAM_ID": "999",
    "RESULTS_CHANNEL_ID": "111",
    "CTF_FORUM_CHANNEL_ID": "222",
    "ADMIN_ROLE_IDS": "1,2,3",
}


def test_settings_loads_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    settings = get_settings()

    assert settings.discord_token == "fake-token"
    assert settings.discord_guild_id == 123456789
    assert settings.admin_role_ids == [1, 2, 3]
    assert settings.ctf_resource_retention_days == 60
    assert settings.public_api_origins == []


def test_settings_missing_required_raises_actionable_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DISCORD_TOKEN", "fake-token")

    with pytest.raises(SettingsError) as exc_info:
        get_settings()

    assert ".env.example" in str(exc_info.value)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ht_manager.config'`.

- [ ] **Step 3: Write `src/ht_manager/config.py`**

```python
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(Exception):
    """Raised when required configuration is missing or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_token: str
    discord_guild_id: int
    database_url: str
    ctftime_team_id: str
    results_channel_id: int
    ctf_forum_channel_id: int
    admin_role_ids: list[int]
    member_role_id: int | None = None
    bot_log_channel_id: int | None = None
    ctf_resource_retention_days: int = 60
    public_api_origins: list[str] = []
    log_level: str = "INFO"

    @field_validator("admin_role_ids", mode="before")
    @classmethod
    def _split_admin_role_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(item) for item in value.split(",") if item.strip()]
        return value

    @field_validator("public_api_origins", mode="before")
    @classmethod
    def _split_public_api_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


def get_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:
        raise SettingsError(
            "Invalid or missing configuration. Check your .env file against "
            f".env.example. Details: {exc}"
        ) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Write `.env.example`**

```
# .env.example — never commit real values
DISCORD_TOKEN=
DISCORD_GUILD_ID=
DATABASE_URL=postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager
CTFTIME_TEAM_ID=
RESULTS_CHANNEL_ID=
CTF_FORUM_CHANNEL_ID=
ADMIN_ROLE_IDS=
MEMBER_ROLE_ID=
BOT_LOG_CHANNEL_ID=
CTF_RESOURCE_RETENTION_DAYS=60
PUBLIC_API_ORIGINS=https://hackertroupe.dev
LOG_LEVEL=INFO
```

- [ ] **Step 6: Run the full test suite and lint**

```bash
ruff check .
pytest
```

Expected: both pass.

- [ ] **Step 7: Commit**

```bash
git add src/ht_manager/config.py .env.example tests/test_config.py
git commit -m "feat: add settings loading with actionable validation errors"
```

---

### Task 3: Docker Compose Postgres and Dockerfile

**Files:**
- Create: `docker-compose.yml`
- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `pyproject.toml` (Task 1) to build the image; `.env` (developer-created from `.env.example`, Task 2) at container runtime.
- Produces: a `postgres` service reachable at `localhost:5432` with user/password/db `ht_manager`/`ht_manager`/`ht_manager` — later tasks' `DATABASE_URL` defaults point at this. No automated test; verified manually since this is infrastructure config, not application code (consistent with spec §21's scope for the automated suite).

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: ht_manager
      POSTGRES_PASSWORD: ht_manager
      POSTGRES_DB: ht_manager
    ports:
      - "5432:5432"
    volumes:
      - ht_manager_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ht_manager"]
      interval: 5s
      timeout: 5s
      retries: 5

  ht-manager-bot:
    build: .
    command: python -m ht_manager.main
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy

  ht-manager-api:
    build: .
    command: uvicorn ht_manager.api.app:app --host 0.0.0.0 --port 8000
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  ht_manager_postgres_data:
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

CMD ["python", "-m", "ht_manager.main"]
```

- [ ] **Step 3: Write `.dockerignore`**

```
.venv
__pycache__
*.pyc
.git
.env
tests
.pytest_cache
.ruff_cache
```

- [ ] **Step 4: Verify Postgres comes up healthy**

```bash
docker compose up -d postgres
docker compose ps
docker compose exec postgres pg_isready -U ht_manager
```

Expected: `pg_isready` reports `accepting connections`; `docker compose ps` shows `postgres` as `healthy`.

- [ ] **Step 5: Tear down**

```bash
docker compose down
```

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml Dockerfile .dockerignore
git commit -m "chore: add Docker Compose Postgres and app Dockerfile"
```

---

### Task 4: Async DB engine and session

**Files:**
- Create: `src/ht_manager/db/base.py`
- Create: `src/ht_manager/db/session.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db_session.py`

**Interfaces:**
- Consumes: a running Postgres reachable via `TEST_DATABASE_URL` env var, defaulting to the Task 3 compose service (`postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager`). Requires `docker compose up -d postgres` (Task 3) to be running before these tests.
- Produces: `Base` (SQLAlchemy `DeclarativeBase` subclass, used by Alembic in Task 5 and by every model from M1 onward), `create_engine(database_url: str) -> AsyncEngine`, `create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]`. Deliberately takes an explicit `database_url` rather than reading `Settings` directly, so the DB layer is testable without full app configuration (spec §2.1: every service independently testable). `tests/conftest.py` provides a `db_session` fixture other test modules can reuse from M1 onward.

- [ ] **Step 1: Write the failing test**

`tests/conftest.py`:

```python
import os

import pytest_asyncio

from ht_manager.db.session import create_engine, create_session_factory

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager",
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_engine(TEST_DATABASE_URL)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

`tests/test_db_session.py`:

```python
from sqlalchemy import text


async def test_db_session_can_execute_query(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose up -d postgres
pytest tests/test_db_session.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ht_manager.db.session'`.

- [ ] **Step 3: Write `src/ht_manager/db/base.py`**

```python
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 4: Write `src/ht_manager/db/session.py`**

```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_db_session.py -v
```

Expected: PASS.

- [ ] **Step 6: Run the full test suite and lint**

```bash
ruff check .
pytest
```

Expected: both pass.

- [ ] **Step 7: Commit**

```bash
git add src/ht_manager/db/base.py src/ht_manager/db/session.py tests/conftest.py tests/test_db_session.py
git commit -m "feat: add async SQLAlchemy engine and session factory"
```

---

### Task 5: Alembic migration scaffold

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/0001_baseline.py`

**Interfaces:**
- Consumes: `Base` from `src/ht_manager/db/base.py` (Task 4); `DATABASE_URL` env var at migration-run time (read directly, not via `Settings`, so migrations can run in contexts — like CI — that don't have the full bot config).
- Produces: a working `alembic upgrade head` / `alembic downgrade base` cycle against Postgres, with an empty baseline migration (no domain tables yet — those arrive in M1's plan). Later milestones add migrations with `alembic revision --autogenerate -m "..."` against `target_metadata = Base.metadata`.

- [ ] **Step 1: Write `alembic.ini`**

```ini
[alembic]
script_location = migrations

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Write `migrations/env.py`**

```python
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncConnection, async_engine_from_config

from ht_manager.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set to run migrations")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: AsyncConnection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 3: Write `migrations/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Write the baseline migration `migrations/versions/0001_baseline.py`**

```python
"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-08-04

"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
```

- [ ] **Step 5: Run the migration against the running Postgres and verify it applies and reverses cleanly**

```bash
docker compose up -d postgres
export DATABASE_URL=postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager
alembic upgrade head
docker compose exec postgres psql -U ht_manager -c "\dt"
alembic downgrade base
alembic upgrade head
```

Expected: `alembic upgrade head` succeeds and creates an `alembic_version` table (visible in `\dt`); `alembic downgrade base` and the subsequent `alembic upgrade head` both succeed without error, proving the migration is reversible per §5.1.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini migrations
git commit -m "chore: wire up async Alembic migrations with empty baseline"
```

---

### Task 6: Discord bot skeleton and `/ping` command

**Files:**
- Create: `src/ht_manager/bot/client.py`
- Create: `src/ht_manager/bot/commands/ping.py`
- Create: `src/ht_manager/main.py`
- Test: `tests/test_ping.py`

**Interfaces:**
- Consumes: `Settings` and `get_settings()` from `src/ht_manager/config.py` (Task 2).
- Produces: `ping_reply(latency_seconds: float) -> str` (pure function, unit tested directly — no live Discord connection needed, per spec §21 "mock Discord API boundaries"), `register_ping_command(bot: commands.Bot) -> None`, `HTManagerBot` (discord.py `commands.Bot` subclass), `build_bot(settings: Settings) -> HTManagerBot`, and `main() -> None` as the process entrypoint used by `Dockerfile`'s `CMD` and the `ht-manager-bot` compose service (Task 3).

- [ ] **Step 1: Write the failing test**

`tests/test_ping.py`:

```python
from ht_manager.bot.commands.ping import ping_reply


def test_ping_reply_formats_milliseconds():
    assert ping_reply(0.123) == "Pong! 123ms"


def test_ping_reply_handles_zero_latency():
    assert ping_reply(0.0) == "Pong! 0ms"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_ping.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ht_manager.bot.commands.ping'`.

- [ ] **Step 3: Write `src/ht_manager/bot/commands/ping.py`**

```python
from __future__ import annotations

import discord
from discord.ext.commands import Bot


def ping_reply(latency_seconds: float) -> str:
    return f"Pong! {latency_seconds * 1000:.0f}ms"


def register_ping_command(bot: Bot) -> None:
    @bot.tree.command(name="ping", description="Health/latency check")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(ping_reply(bot.latency))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_ping.py -v
```

Expected: PASS.

- [ ] **Step 5: Write `src/ht_manager/bot/client.py`**

```python
from __future__ import annotations

import discord
from discord.ext import commands

from ht_manager.bot.commands.ping import register_ping_command
from ht_manager.config import Settings


class HTManagerBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings

    async def setup_hook(self) -> None:
        register_ping_command(self)
        guild = discord.Object(id=self.settings.discord_guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)


def build_bot(settings: Settings) -> HTManagerBot:
    return HTManagerBot(settings)
```

- [ ] **Step 6: Write `src/ht_manager/main.py`**

```python
from __future__ import annotations

from ht_manager.bot.client import build_bot
from ht_manager.config import get_settings


def main() -> None:
    settings = get_settings()
    bot = build_bot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the full test suite and lint**

```bash
ruff check .
pytest
```

Expected: both pass. (This does not start a live Discord connection — that's verified manually in Step 8.)

- [ ] **Step 8: Manual verification with a real bot token**

Fill in a real `.env` (copied from `.env.example`, Task 2) with a valid `DISCORD_TOKEN` and `DISCORD_GUILD_ID` for a test server you control, then:

```bash
docker compose up -d postgres
docker compose up --build ht-manager-bot
```

Expected: bot logs in without error; running `/ping` in the configured Discord server returns `Pong! <n>ms`.

- [ ] **Step 9: Commit**

```bash
git add src/ht_manager/bot src/ht_manager/main.py tests/test_ping.py
git commit -m "feat: add Discord bot skeleton with /ping command"
```

---

### Task 7: FastAPI `/health` endpoint

**Files:**
- Create: `src/ht_manager/api/app.py`
- Test: `tests/test_api_health.py`

**Interfaces:**
- Consumes: nothing beyond the package scaffold (Task 1).
- Produces: `create_app() -> FastAPI` and a module-level `app` instance, used by `uvicorn ht_manager.api.app:app` in the `ht-manager-api` compose service (Task 3). `GET /health` returns `{"status": "ok"}` per spec §13/§20.

- [ ] **Step 1: Write the failing test**

`tests/test_api_health.py`:

```python
from fastapi.testclient import TestClient

from ht_manager.api.app import create_app


def test_health_returns_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_api_health.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ht_manager.api.app'`.

- [ ] **Step 3: Write `src/ht_manager/api/app.py`**

```python
from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="HT-Manager API", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_api_health.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite and lint**

```bash
ruff check .
pytest
```

Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add src/ht_manager/api/app.py tests/test_api_health.py
git commit -m "feat: add FastAPI app with /health endpoint"
```

---

### Task 8: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `pyproject.toml` (Task 1), the full test suite (Tasks 2, 4, 6, 7), and a Postgres service container providing the same `DATABASE_URL`/`TEST_DATABASE_URL` shape as local dev (Task 3/4).
- Produces: a GitHub Actions workflow that runs Ruff and pytest on every push/PR. No later task depends on this one.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: ht_manager
          POSTGRES_PASSWORD: ht_manager
          POSTGRES_DB: ht_manager
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U ht_manager"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5

    env:
      DATABASE_URL: postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager
      TEST_DATABASE_URL: postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Lint
        run: ruff check .

      - name: Run migrations
        run: alembic upgrade head

      - name: Run tests
        run: pytest
```

- [ ] **Step 2: Verify the YAML is syntactically valid**

```bash
pip install --quiet pyyaml
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"
```

Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "chore: add CI workflow for lint, migrations, and tests"
```

---

### Task 9: README and final verification pass

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: every previous task's local-dev commands, consolidated into one document.
- Produces: nothing later tasks depend on — this is the last task in M0.

- [ ] **Step 1: Write `README.md`**

```markdown
# HT-Manager

Discord bot and API for HackerTroupe's CTF operations: curating and polling
the next CTF, tracking participation, syncing/announcing CTFTime results,
and exposing structured data to hackertroupe.dev.

Full design: `docs/superpowers/specs/2026-08-04-ht-manager-design.md`.

## Local development

1. Copy `.env.example` to `.env` and fill in real values (Discord bot
   token, guild ID, channel/role IDs, CTFTime team ID). Never commit `.env`.
2. Start Postgres:
   ```bash
   docker compose up -d postgres
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
5. Run tests and lint:
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
   uvicorn ht_manager.api.app:app --reload
   ```

Or run everything through Compose once `.env` is filled in:

```bash
docker compose up --build
```

## Project status

M0 (Foundation) complete: config loading, Postgres + Alembic, bot login,
`/ping`, `/health`, CI. See the spec's milestone table (§25) for what's next.
```

- [ ] **Step 2: Run the full verification pass**

```bash
ruff check .
pytest
```

Expected: both pass with zero errors — this is the exit criteria for M0.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add local development README for M0"
```

---

## M0 Exit Criteria

- `docker compose up -d postgres && alembic upgrade head` succeeds from a clean checkout.
- `pytest` and `ruff check .` both pass.
- With a real `.env`, `python -m ht_manager.main` logs the bot into Discord and `/ping` responds.
- `uvicorn ht_manager.api.app:app` serves `GET /health` → `{"status": "ok"}`.
- CI runs lint + migrations + tests on push.
- README documents the full local setup from a clean checkout.

This satisfies the M0 row of the spec's milestone table (§25): "Repository, config, Docker Postgres, SQLAlchemy/Alembic, bot login, `/ping`, tests/CI." M1 (CTF Data — CTF models, CTFTime client, `/addctf`, `/editctf`, draft lifecycle) gets its own plan once this one ships.
