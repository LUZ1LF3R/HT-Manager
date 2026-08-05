from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf_category_stat import CTFCategoryStat


async def add(session: AsyncSession, stat: CTFCategoryStat) -> CTFCategoryStat:
    session.add(stat)
    await session.flush()
    return stat


async def get(session: AsyncSession, *, ctf_id: int, category_name: str) -> CTFCategoryStat | None:
    result = await session.execute(
        select(CTFCategoryStat).where(
            CTFCategoryStat.ctf_id == ctf_id, CTFCategoryStat.category_name == category_name
        )
    )
    return result.scalar_one_or_none()


async def list_for_ctf(session: AsyncSession, ctf_id: int) -> list[CTFCategoryStat]:
    result = await session.execute(
        select(CTFCategoryStat)
        .where(CTFCategoryStat.ctf_id == ctf_id)
        .order_by(CTFCategoryStat.category_name)
    )
    return list(result.scalars().all())
