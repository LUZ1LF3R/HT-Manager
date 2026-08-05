from __future__ import annotations

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.services import summary as summary_service


def register_setcategory_command(bot: Bot) -> None:
    @bot.tree.command(name="setcategory", description="Set or correct one category's solved/total")
    @admin_only()
    @discord.app_commands.describe(
        ctf_id="ID of the CTF",
        category="Category name (e.g. Web, Pwn, Rev)",
        solved="Number solved",
        total="Total challenges in this category",
    )
    async def setcategory(
        interaction: discord.Interaction, ctf_id: int, category: str, solved: int, total: int
    ) -> None:
        if solved > total or solved < 0 or total < 0:
            await interaction.response.send_message(
                "solved must be between 0 and total.", ephemeral=True
            )
            return

        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        try:
            async with session_factory() as session, session.begin():
                stat = await summary_service.set_category_stat(
                    session,
                    actor_discord_id=interaction.user.id,
                    ctf_id=ctf_id,
                    category_name=category,
                    solved=solved,
                    total=total,
                )
        except summary_service.CTFNotFoundError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(
            f"CTF #{ctf_id}: {stat.category_name} set to {stat.solved}/{stat.total}."
        )
