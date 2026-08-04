from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ht_manager.api.app import create_app
from ht_manager.api.dependencies import get_session
from ht_manager.bot.client import HTManagerBot, build_bot
from ht_manager.config import Settings
from ht_manager.db.session import create_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ht_manager:ht_manager@localhost:5432/ht_manager_test",
)


@pytest.fixture(scope="session", autouse=True)
def _migrated_test_database() -> None:
    """Run Alembic migrations against TEST_DATABASE_URL once per test session.

    migrations/env.py reads DATABASE_URL from the environment directly, so
    it's swapped for the duration of this call rather than threaded through
    alembic's Config.
    """
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        command.upgrade(Config("alembic.ini"), "head")
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
        ctf_forum_channel_id=222,
        admin_role_ids=[1, 2, 3],
        member_role_id=None,
        bot_log_channel_id=None,
    )


@pytest.fixture
def api_app(settings: Settings, db_session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    """The FastAPI app with `get_session` AND `app.state.session_factory`
    both pointed at the test's isolated, rolled-back session factory, so
    both the documented DI path and any direct `request.app.state` access
    stay isolated. Exposed separately from `api_client` so tests can add a
    route to prove the override actually works end-to-end."""
    app = create_app(settings)
    app.state.session_factory = db_session_factory

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    return app


@pytest_asyncio.fixture
async def api_client(
    api_app: FastAPI, db_session_factory: async_sessionmaker[AsyncSession]
) -> AsyncIterator[httpx.AsyncClient]:
    """Uses httpx's ASGI transport directly rather than FastAPI's
    (synchronous) TestClient: TestClient drives the app from a separate
    thread with its own event loop, which breaks `api_app`'s session
    override the moment a route actually awaits it — asyncpg connections
    are bound to the loop that created them.

    `ASGITransport` doesn't emit lifespan events, so `create_app()`'s
    lifespan (which would overwrite `app.state.session_factory` with a real
    engine) never runs here — that's *why* `api_app`'s pre-set isolated
    factory survives. The assertion below guards that invariant: if a
    future change wraps this in something that does run lifespan (e.g.
    `asgi_lifespan.LifespanManager`, often reached for to test startup
    code), this fails loudly instead of silently serving requests against a
    real, un-isolated database.
    """
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert api_app.state.session_factory is db_session_factory
        yield client


@pytest.fixture
def bot(settings: Settings, db_session_factory: async_sessionmaker[AsyncSession]) -> HTManagerBot:
    """A bot instance wired to the test's isolated session factory, for
    tests that need `bot.session_factory` to actually work."""
    return build_bot(settings, db_session_factory)
