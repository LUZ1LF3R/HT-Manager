from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.sync_state import SyncState


async def get(session: AsyncSession, integration_key: str) -> SyncState | None:
    result = await session.execute(
        select(SyncState).where(SyncState.integration_key == integration_key)
    )
    return result.scalar_one_or_none()


async def add(session: AsyncSession, sync_state: SyncState) -> SyncState:
    session.add(sync_state)
    await session.flush()
    return sync_state
