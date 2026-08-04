from __future__ import annotations

import discord
from discord.ext import commands

from ht_manager.bot.commands.ping import register_ping_command
from ht_manager.config import Settings


class HTManagerBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings

    async def setup_hook(self) -> None:
        register_ping_command(self)
        guild = discord.Object(id=self.settings.discord_guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)


def build_bot(settings: Settings) -> HTManagerBot:
    return HTManagerBot(settings)
