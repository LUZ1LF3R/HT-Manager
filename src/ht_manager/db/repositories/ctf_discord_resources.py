from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf_discord_resource import CTFDiscordResource


async def add(session: AsyncSession, resource: CTFDiscordResource) -> CTFDiscordResource:
    session.add(resource)
    await session.flush()
    return resource


async def get_by_ctf_id(session: AsyncSession, ctf_id: int) -> CTFDiscordResource | None:
    result = await session.execute(
        select(CTFDiscordResource).where(CTFDiscordResource.ctf_id == ctf_id)
    )
    return result.scalar_one_or_none()


async def list_due_for_cleanup(session: AsyncSession, now) -> list[CTFDiscordResource]:
    result = await session.execute(
        select(CTFDiscordResource).where(
            CTFDiscordResource.cleaned_at.is_(None),
            CTFDiscordResource.cleanup_after.is_not(None),
            CTFDiscordResource.cleanup_after <= now,
        )
    )
    return list(result.scalars().all())
