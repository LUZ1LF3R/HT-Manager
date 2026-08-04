from __future__ import annotations

import discord
from discord.ext.commands import Bot


def ping_reply(latency_seconds: float) -> str:
    return f"Pong! {latency_seconds * 1000:.0f}ms"


def register_ping_command(bot: Bot) -> None:
    @bot.tree.command(name="ping", description="Health/latency check")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(ping_reply(bot.latency))
