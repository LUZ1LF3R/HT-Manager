from __future__ import annotations

from typing import Any

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.services import results as results_service


def register_editresult_command(bot: Bot) -> None:
    @bot.tree.command(name="editresult", description="Correct a CTF's recorded result")
    @admin_only()
    @discord.app_commands.describe(
        ctf_id="ID of the CTF",
        placement="Final placement",
        total_teams="Total teams in the scoreboard",
        score="Score",
        source_url="Link to the scoreboard/writeup",
        notes="Any extra context",
    )
    async def editresult(
        interaction: discord.Interaction,
        ctf_id: int,
        placement: int | None = None,
        total_teams: int | None = None,
        score: float | None = None,
        source_url: str | None = None,
        notes: str | None = None,
    ) -> None:
        changes: dict[str, Any] = {}
        for name, value in (
            ("placement", placement),
            ("total_teams", total_teams),
            ("score", score),
            ("source_url", source_url),
            ("notes", notes),
        ):
            if value is not None:
                changes[name] = value

        if not changes:
            await interaction.response.send_message("No fields provided to update.", ephemeral=True)
            return

        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        try:
            async with session_factory() as session, session.begin():
                result = await results_service.edit_result(
                    session, actor_discord_id=interaction.user.id, ctf_id=ctf_id, **changes
                )
        except results_service.ResultNotFoundError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(
            f"Updated result for CTF #{ctf_id}: placement {result.placement}."
        )
