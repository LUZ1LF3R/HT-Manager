from __future__ import annotations

import logging
from datetime import UTC, datetime

import discord
from discord.ext.commands import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_manager.db.models.poll import PollStatus
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import polls as polls_repo
from ht_manager.services import polls as polls_service

logger = logging.getLogger(__name__)


async def close_expired_polls(bot: Bot, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Finalizes any `OPEN` poll past its `closes_at` (spec §7.1 step 12).

    Idempotent: `polls_service.finalize` rejects a poll that isn't `OPEN`
    anymore, so re-running this against an already-closed poll is a no-op —
    safe for the scheduler to retry or overlap runs (spec §18).
    """
    async with session_factory() as session:
        expired = await polls_repo.list_expired_open(session, datetime.now(UTC))

    for poll in expired:
        try:
            channel = bot.get_channel(poll.channel_id) or await bot.fetch_channel(poll.channel_id)
            message = await channel.fetch_message(poll.discord_message_id)
        except discord.HTTPException:
            logger.exception("Could not fetch poll message for poll_id=%s", poll.id)
            continue

        if message.poll is None:
            logger.warning("Message for poll_id=%s no longer has a poll attached", poll.id)
            continue

        async with session_factory() as session:
            options = await polls_repo.list_options(session, poll.id)
        ctf_by_index = {option.option_index: option.ctf_id for option in options}

        votes: dict[int, list[int]] = {ctf_id: [] for ctf_id in ctf_by_index.values()}
        for index, answer in enumerate(message.poll.answers):
            ctf_id = ctf_by_index.get(index)
            if ctf_id is None:
                continue
            async for voter in answer.voters():
                if voter.bot:
                    continue
                votes[ctf_id].append(voter.id)

        async with session_factory() as session, session.begin():
            finalized = await polls_service.finalize(
                session, actor_discord_id=bot.user.id, poll_id=poll.id, votes=votes
            )
            summary = await _summarize(session, finalized)

        try:
            await channel.send(summary)
        except discord.HTTPException:
            logger.exception("Could not announce poll outcome for poll_id=%s", poll.id)

        if finalized.status is PollStatus.CLOSED and finalized.winning_ctf_id is not None:
            await _setup_winner(bot, session_factory, channel, finalized.winning_ctf_id)


async def _setup_winner(bot: Bot, session_factory, channel, ctf_id: int) -> None:
    settings = bot.settings  # type: ignore[attr-defined]
    try:
        await polls_service.setup_ctf_resources(
            session_factory,
            actor_discord_id=bot.user.id,
            bot=bot,
            ctf_id=ctf_id,
            guild_id=settings.discord_guild_id,
            forum_channel_id=settings.ctf_forum_channel_id,
        )
    except Exception:
        logger.exception("Winner-resolution setup failed for ctf_id=%s", ctf_id)
        if settings.bot_log_channel_id:
            log_channel = bot.get_channel(settings.bot_log_channel_id)
            if log_channel is not None:
                await log_channel.send(
                    f"Setup failed for CTF #{ctf_id} after poll close. Run /setupctf to retry."
                )


async def _summarize(session: AsyncSession, poll) -> str:
    if poll.status is PollStatus.CLOSED and poll.winning_ctf_id is not None:
        ctf = await ctfs_repo.get(session, poll.winning_ctf_id)
        name = ctf.name if ctf is not None else f"CTF #{poll.winning_ctf_id}"
        return f"Poll closed — **{name}** wins! An admin will run /setupctf to finalize setup."
    if poll.status is PollStatus.TIED:
        return "Poll closed in a tie — an admin needs to run /resolvepoll to pick the winner."
    return "Poll closed with no votes — nothing was selected. Run /nextctf again when ready."
