from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTF, CTFStatus

NON_TERMINAL_STATUSES = (
    CTFStatus.POLLING,
    CTFStatus.SELECTED,
    CTFStatus.ACTIVE,
    CTFStatus.TIED,
)


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


async def list_non_terminal(session: AsyncSession) -> list[CTF]:
    result = await session.execute(select(CTF).where(CTF.status.in_(NON_TERMINAL_STATUSES)))
    return list(result.scalars().all())


RESULT_ELIGIBLE_STATUSES = (CTFStatus.ACTIVE, CTFStatus.FINISHED, CTFStatus.ARCHIVED)


async def list_awaiting_result_sync(session: AsyncSession, now) -> list[CTF]:
    """CTFs we actually ran, past their end date, tracked on CTFTime —
    the candidate set for the 12-hour result sync (spec §10)."""
    result = await session.execute(
        select(CTF).where(
            CTF.status.in_(RESULT_ELIGIBLE_STATUSES),
            CTF.ctftime_event_id.is_not(None),
            CTF.end_at <= now,
        )
    )
    return list(result.scalars().all())
