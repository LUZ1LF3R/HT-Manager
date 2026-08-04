from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for routes that need a DB session, e.g.
    `session: AsyncSession = Depends(get_session)`.

    Kept out of `app.py` deliberately: a route module needs to import this,
    and `app.py` needs to `include_router()` that same module, which would
    be a circular import if `get_session` lived in `app.py`.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session
