from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.result import Result


async def add(session: AsyncSession, result: Result) -> Result:
    session.add(result)
    await session.flush()
    return result


async def get_by_ctf_id(session: AsyncSession, ctf_id: int) -> Result | None:
    query_result = await session.execute(select(Result).where(Result.ctf_id == ctf_id))
    return query_result.scalar_one_or_none()
