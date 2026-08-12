from __future__ import annotations

import discord
from discord.ext.commands import Bot

from ht_manager.bot.formatting import code_block
from ht_manager.services import summary as summary_service


def register_summary_command(bot: Bot) -> None:
    """`/summary` — renders a CTF's summary without changing its status.

    `/endctf` prints the summary once, at the moment it finishes the CTF, but
    category stats are usually entered *after* an event ends. Without a
    read-only view, a `/setcategory` correction made afterwards would update
    the database with no way to see the corrected result.
    """

    @bot.tree.command(name="summary", description="Show a CTF's summary without changing it")
    @discord.app_commands.describe(ctf_id="ID of the CTF")
    async def summary(interaction: discord.Interaction, ctf_id: int) -> None:
        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        try:
            async with session_factory() as session:
                rendered = await summary_service.render_summary(session, ctf_id)
        except summary_service.CTFNotFoundError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(code_block(rendered))
