from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_manager.bot.commands.addctf import register_addctf_command
from ht_manager.bot.commands.editctf import register_editctf_command
from ht_manager.bot.commands.ping import register_ping_command
from ht_manager.config import Settings

logger = logging.getLogger(__name__)


class HTManagerBot(commands.Bot):
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.session_factory = session_factory

    async def setup_hook(self) -> None:
        register_ping_command(self)
        register_addctf_command(self)
        register_editctf_command(self)
        self.tree.on_error = self._on_app_command_error
        guild = discord.Object(id=self.settings.discord_guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            logger.warning(
                "Permission denied for /%s (user_id=%s)",
                interaction.command.name if interaction.command else "?",
                interaction.user.id,
            )
            message = "You don't have permission to use this command."
        else:
            logger.exception("Unhandled app command error", exc_info=error)
            message = "Something went wrong running that command."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            logger.warning("Could not deliver error reply to user_id=%s", interaction.user.id)


def build_bot(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> HTManagerBot:
    return HTManagerBot(settings, session_factory)
