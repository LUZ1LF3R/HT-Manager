from __future__ import annotations

import logging

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import polls as polls_service

logger = logging.getLogger(__name__)


async def _finish_setup(interaction: discord.Interaction, ctf_id: int) -> str:
    bot = interaction.client
    settings = bot.settings  # type: ignore[attr-defined]
    try:
        await polls_service.setup_ctf_resources(
            bot.session_factory,  # type: ignore[attr-defined]
            actor_discord_id=interaction.user.id,
            bot=bot,
            ctf_id=ctf_id,
            guild_id=settings.discord_guild_id,
            forum_channel_id=settings.ctf_forum_channel_id,
            retention_days=settings.ctf_resource_retention_days,
        )
    except Exception:
        logger.exception("Winner-resolution setup failed for ctf_id=%s", ctf_id)
        if settings.bot_log_channel_id:
            channel = bot.get_channel(settings.bot_log_channel_id)
            if channel is not None:
                await channel.send(
                    f"Setup failed for CTF #{ctf_id} after poll resolution. Run /setupctf to retry."
                )
        return (
            "Winner recorded, but role/workspace setup failed. "
            "An admin can retry with /setupctf."
        )
    return "Winner recorded and the CTF role/workspace are set up."


def register_resolvepoll_command(bot: Bot) -> None:
    @bot.tree.command(name="resolvepoll", description="Manually pick the winner of a tied poll")
    @admin_only()
    @discord.app_commands.describe(ctf_id="ID of the tied CTF to declare the winner")
    async def resolvepoll(interaction: discord.Interaction, ctf_id: int) -> None:
        await interaction.response.defer()
        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]

        try:
            async with session_factory() as session, session.begin():
                await polls_service.resolve_tie(
                    session, actor_discord_id=interaction.user.id, ctf_id=ctf_id
                )
        except (
            polls_service.PollNotFoundError,
            polls_service.InvalidPollStateError,
            ctfs_service.CTFNotFoundError,
        ) as exc:
            await interaction.followup.send(str(exc))
            return

        message = await _finish_setup(interaction, ctf_id)
        await interaction.followup.send(message)
