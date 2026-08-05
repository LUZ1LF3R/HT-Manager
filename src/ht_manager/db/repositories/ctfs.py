from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTF


async def add(session: AsyncSession, ctf: CTF) -> CTF:
    session.add(ctf)
    await session.flush()
    return ctf


async def get(session: AsyncSession, ctf_id: int) -> CTF | None:
    return await session.get(CTF, ctf_id)


async def get_by_ctftime_event_id(session: AsyncSession, ctftime_event_id: int) -> CTF | None:
    result = await session.execute(select(CTF).where(CTF.ctftime_event_id == ctftime_event_id))
    return result.scalar_one_or_none()


async def delete(session: AsyncSession, ctf: CTF) -> None:
    await session.delete(ctf)
    await session.flush()
