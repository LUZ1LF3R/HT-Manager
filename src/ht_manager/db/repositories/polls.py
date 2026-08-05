from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.poll import Poll, PollOption, PollStatus, PollVote


async def add_poll(session: AsyncSession, poll: Poll) -> Poll:
    session.add(poll)
    await session.flush()
    return poll


async def get(session: AsyncSession, poll_id: int) -> Poll | None:
    return await session.get(Poll, poll_id)


async def list_options(session: AsyncSession, poll_id: int) -> list[PollOption]:
    result = await session.execute(
        select(PollOption).where(PollOption.poll_id == poll_id).order_by(PollOption.option_index)
    )
    return list(result.scalars().all())


async def add_option(session: AsyncSession, option: PollOption) -> PollOption:
    session.add(option)
    await session.flush()
    return option


async def delete_option(session: AsyncSession, option: PollOption) -> None:
    await session.delete(option)
    await session.flush()


async def delete_poll(session: AsyncSession, poll: Poll) -> None:
    await session.delete(poll)
    await session.flush()


async def add_vote(session: AsyncSession, vote: PollVote) -> PollVote:
    session.add(vote)
    await session.flush()
    return vote


async def list_expired_open(session: AsyncSession, now: datetime) -> list[Poll]:
    result = await session.execute(
        select(Poll).where(Poll.status == PollStatus.OPEN, Poll.closes_at <= now)
    )
    return list(result.scalars().all())
