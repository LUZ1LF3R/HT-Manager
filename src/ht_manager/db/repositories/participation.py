from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.participation import Participation


async def add(session: AsyncSession, participation: Participation) -> Participation:
    session.add(participation)
    await session.flush()
    return participation


async def get(session: AsyncSession, *, ctf_id: int, discord_user_id: int) -> Participation | None:
    result = await session.execute(
        select(Participation).where(
            Participation.ctf_id == ctf_id, Participation.discord_user_id == discord_user_id
        )
    )
    return result.scalar_one_or_none()


async def list_for_ctf(session: AsyncSession, ctf_id: int) -> list[Participation]:
    result = await session.execute(select(Participation).where(Participation.ctf_id == ctf_id))
    return list(result.scalars().all())


async def list_for_member(session: AsyncSession, discord_user_id: int) -> list[Participation]:
    result = await session.execute(
        select(Participation).where(Participation.discord_user_id == discord_user_id)
    )
    return list(result.scalars().all())


async def delete(session: AsyncSession, participation: Participation) -> None:
    await session.delete(participation)
    await session.flush()
