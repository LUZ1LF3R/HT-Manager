from __future__ import annotations

import os
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ht_manager.bot.client import HTManagerBot, build_bot
from ht_manager.config import Settings
from ht_manager.db.session import create_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager_test",
)


@pytest.fixture(scope="session")
def _migrated_test_database() -> None:
    """Run Alembic migrations against TEST_DATABASE_URL once per test session.

    Deliberately *not* autouse: only `_engine` depends on it, so tests that
    never touch the database (config parsing, the CTFTime client against a
    mock transport, permission predicates) still run with no Postgres
    available. Making this autouse meant every test in the suite failed with
    a connection error when Postgres was down.

    migrations/env.py reads DATABASE_URL from the environment directly, so
    it's swapped for the duration of this call rather than threaded through
    alembic's Config.

    That same env.py ends in `asyncio.run(...)`, which unsets the *calling
    thread's* current event loop when it finishes — including pytest-asyncio's
    session-scoped loop, which every async test then runs on. Doing the
    upgrade on its own thread keeps that thread-local damage away from the
    main thread; `.result()` still re-raises any migration failure. The old
    autouse ordering hid this by always running before the loop existed.
    """
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(command.upgrade, Config("alembic.ini"), "head").result()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest_asyncio.fixture(scope="session")
async def _engine(_migrated_test_database: None) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(
    _engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A sessionmaker bound to a single connection inside a rolled-back
    transaction, so anything built from it in a test — a raw `db_session`,
    a bot, or an API client — can insert and commit freely without touching
    the database's persistent state or needing manual cleanup."""
    connection = await _engine.connect()
    transaction = await connection.begin()
    session_factory = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session_factory
    finally:
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with db_session_factory() as session:
        yield session


@pytest.fixture
def settings() -> Settings:
    return Settings(
        discord_token="fake-token",
        discord_guild_id=123,
        database_url=TEST_DATABASE_URL,
        ctftime_team_id="999",
        results_channel_id=111,
        ctf_category_id=222,
        ctf_archive_category_id=333,
        admin_role_ids=[1, 2, 3],
        member_role_id=None,
        bot_log_channel_id=None,
    )


@pytest.fixture
def bot(settings: Settings, db_session_factory: async_sessionmaker[AsyncSession]) -> HTManagerBot:
    """A bot instance wired to the test's isolated session factory, for
    tests that need `bot.session_factory` to actually work."""
    return build_bot(settings, db_session_factory)


@pytest.fixture
def offline_bot(settings: Settings) -> HTManagerBot:
    """A bot whose session factory is never used — for tests about the bot
    itself (error handling, permissions) that shouldn't need a database just
    to construct one."""
    return build_bot(settings, async_sessionmaker())
