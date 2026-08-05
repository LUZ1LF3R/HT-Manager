from __future__ import annotations

import logging
from datetime import UTC, datetime

from discord.ext.commands import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_manager.db.repositories import ctf_discord_resources as resources_repo
from ht_manager.services import discord_resources

logger = logging.getLogger(__name__)


async def cleanup_expired_resources(
    bot: Bot, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Removes temporary roles/workspaces past their retention window (spec
    §8). Never touches `ctfs`, `participations`, or `results` — only
    `ctf_discord_resources.cleaned_at` — so history always outlives the
    Discord-side objects (spec §14.3).

    Idempotent: each resource is only fetched via `list_due_for_cleanup`,
    which excludes anything already marked `cleaned_at`, so a retried or
    overlapping run just skips what's already done.
    """
    settings = bot.settings  # type: ignore[attr-defined]
    now = datetime.now(UTC)

    async with session_factory() as session:
        due = await resources_repo.list_due_for_cleanup(session, now)

    for resource in due:
        try:
            if resource.role_id is not None:
                await discord_resources.delete_role(
                    bot, guild_id=settings.discord_guild_id, role_id=resource.role_id
                )
            if resource.thread_id is not None:
                await discord_resources.archive_workspace(
                    bot, guild_id=settings.discord_guild_id, thread_id=resource.thread_id
                )
        except Exception:
            logger.exception("Cleanup failed for ctf_discord_resources.id=%s", resource.id)
            continue

        async with session_factory() as session, session.begin():
            fresh = await resources_repo.get_by_ctf_id(session, resource.ctf_id)
            if fresh is not None:
                await resources_repo.mark_cleaned(session, fresh, now)
