from __future__ import annotations

import discord
from discord.ext.commands import Bot

from ht_manager.bot.formatting import truncate_for_discord
from ht_manager.db.repositories import participation as participation_repo


def register_ctfmembers_command(bot: Bot) -> None:
    @bot.tree.command(name="ctfmembers", description="Show participants for a CTF")
    @discord.app_commands.describe(ctf_id="ID of the CTF")
    async def ctfmembers(interaction: discord.Interaction, ctf_id: int) -> None:
        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        async with session_factory() as session:
            rows = await participation_repo.list_for_ctf(session, ctf_id)

        if not rows:
            await interaction.response.send_message(f"No recorded participants for CTF #{ctf_id}.")
            return

        mentions = "\n".join(f"- <@{row.discord_user_id}> ({row.source.value})" for row in rows)
        await interaction.response.send_message(
            truncate_for_discord(f"Participants for CTF #{ctf_id}:\n{mentions}")
        )
