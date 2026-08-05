from __future__ import annotations

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.services import results as results_service


def register_addresult_command(bot: Bot) -> None:
    @bot.tree.command(name="addresult", description="Record a CTF result manually")
    @admin_only()
    @discord.app_commands.describe(
        ctf_id="ID of the CTF",
        placement="Final placement (e.g. 3 for 3rd)",
        total_teams="Total teams in the scoreboard, if known",
        score="Score, if known",
        source_url="Link to the scoreboard/writeup, if any",
        notes="Any extra context",
    )
    async def addresult(
        interaction: discord.Interaction,
        ctf_id: int,
        placement: int | None = None,
        total_teams: int | None = None,
        score: float | None = None,
        source_url: str | None = None,
        notes: str | None = None,
    ) -> None:
        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        try:
            async with session_factory() as session, session.begin():
                result = await results_service.add_result(
                    session,
                    actor_discord_id=interaction.user.id,
                    ctf_id=ctf_id,
                    placement=placement,
                    total_teams=total_teams,
                    score=score,
                    source_url=source_url,
                    notes=notes,
                )
        except (results_service.CTFNotFoundError, results_service.DuplicateResultError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(
            f"Recorded result for CTF #{ctf_id}: placement {result.placement}."
        )
