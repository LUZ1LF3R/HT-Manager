from __future__ import annotations

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.jobs.result_sync import sync_results


def register_resultsync_command(bot: Bot) -> None:
    @bot.tree.command(name="resultsync", description="Run the CTFTime result sync immediately")
    @admin_only()
    async def resultsync(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        client = interaction.client
        await sync_results(client, client.session_factory)  # type: ignore[attr-defined]
        await interaction.followup.send("Result sync complete.")
