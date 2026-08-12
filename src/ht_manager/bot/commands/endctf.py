from __future__ import annotations

import discord
from discord.ext.commands import Bot

from ht_manager.bot.formatting import code_block
from ht_manager.bot.permissions import admin_only
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import summary as summary_service


def register_endctf_command(bot: Bot) -> None:
    @bot.tree.command(name="endctf", description="Finalize a CTF and post its summary")
    @admin_only()
    @discord.app_commands.describe(ctf_id="ID of the CTF to finish")
    async def endctf(interaction: discord.Interaction, ctf_id: int) -> None:
        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        try:
            async with session_factory() as session, session.begin():
                summary = await summary_service.finish_ctf(
                    session, actor_discord_id=interaction.user.id, ctf_id=ctf_id
                )
        except (summary_service.CTFNotFoundError, ctfs_service.InvalidCTFTransitionError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(code_block(summary))
