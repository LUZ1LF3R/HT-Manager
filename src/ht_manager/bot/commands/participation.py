from __future__ import annotations

import discord
from discord.ext.commands import Bot

from ht_manager.db.repositories import participation as participation_repo


def register_participation_command(bot: Bot) -> None:
    @bot.tree.command(name="participation", description="Show how many CTFs a member has joined")
    @discord.app_commands.describe(member="Member to check (defaults to you)")
    async def participation(
        interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user
        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        async with session_factory() as session:
            rows = await participation_repo.list_for_member(session, target.id)

        await interaction.response.send_message(
            f"{target.mention} has participated in {len(rows)} CTF(s)."
        )
