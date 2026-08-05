from __future__ import annotations

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.services import participation as participation_service


def register_removectfmember_command(bot: Bot) -> None:
    @bot.tree.command(
        name="removectfmember", description="Manually remove a participant from a CTF"
    )
    @admin_only()
    @discord.app_commands.describe(ctf_id="ID of the CTF", member="Member to remove")
    async def removectfmember(
        interaction: discord.Interaction, ctf_id: int, member: discord.Member
    ) -> None:
        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        try:
            async with session_factory() as session, session.begin():
                await participation_service.remove_participation(
                    session,
                    actor_discord_id=interaction.user.id,
                    ctf_id=ctf_id,
                    discord_user_id=member.id,
                )
        except participation_service.ParticipationNotFoundError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(f"Removed {member.mention} from CTF #{ctf_id}.")
