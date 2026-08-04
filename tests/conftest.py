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
