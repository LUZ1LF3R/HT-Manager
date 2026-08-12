from __future__ import annotations

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.db.models.ctf import CTFStatus
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.services import ctfs as ctfs_service


def register_archivectf_command(bot: Bot) -> None:
    @bot.tree.command(name="archivectf", description="Archive a finished CTF")
    @admin_only()
    @discord.app_commands.describe(ctf_id="ID of the CTF to archive")
    async def archivectf(interaction: discord.Interaction, ctf_id: int) -> None:
        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        try:
            async with session_factory() as session, session.begin():
                ctf = await ctfs_repo.get(session, ctf_id)
                if ctf is None:
                    raise ctfs_service.CTFNotFoundError(f"No CTF with ID {ctf_id}.")
                await ctfs_service.transition(
                    session,
                    actor_discord_id=interaction.user.id,
                    ctf=ctf,
                    new_status=CTFStatus.ARCHIVED,
                )
        except (ctfs_service.CTFNotFoundError, ctfs_service.InvalidCTFTransitionError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(f"CTF #{ctf_id} archived.")
