from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTF, CTFStatus
from ht_manager.db.models.result import Result, ResultSource

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

# How long after a CTF ends we keep re-checking CTFTime for its result.
RESULT_SYNC_WINDOW_DAYS = 90


async def list_awaiting_result_sync(session: AsyncSession, now: datetime) -> list[CTF]:
    """CTFs we actually ran, past their end date, tracked on CTFTime, and
    still recent enough to be worth re-checking — the candidate set for the
    12-hour result sync (spec §10).

    Bounded at both ends deliberately. Without the lower bound, every CTF the
    team has ever run would be re-fetched from CTFTime twice a day forever;
    CTFTime publishes standings within days of an event, so a 90-day window is
    already generous and anything later is a job for `/addresult`.

    CTFs whose result was entered or corrected by hand are excluded too: the
    sync refuses to overwrite a `MANUAL` row anyway (see
    `results_service.upsert_from_ctftime`), so there is no point spending a
    request on them.
    """
    manual_result_ctf_ids = select(Result.ctf_id).where(Result.source == ResultSource.MANUAL)
    result = await session.execute(
        select(CTF).where(
            CTF.status.in_(RESULT_ELIGIBLE_STATUSES),
            CTF.ctftime_event_id.is_not(None),
            CTF.end_at <= now,
            CTF.end_at >= now - timedelta(days=RESULT_SYNC_WINDOW_DAYS),
            CTF.id.not_in(manual_result_ctf_ids),
        )
    )
    return list(result.scalars().all())
