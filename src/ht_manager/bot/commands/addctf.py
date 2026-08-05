from __future__ import annotations

from datetime import UTC, datetime

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.services import ctfs as ctfs_service


def parse_iso_datetime(value: str) -> datetime:
    """Accepts ISO-8601; naive input is assumed UTC (spec §7.2: store UTC)."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def register_addctf_command(bot: Bot) -> None:
    @bot.tree.command(name="addctf", description="Add a custom CTF to the database as a draft")
    @admin_only()
    @discord.app_commands.describe(
        name="Display/event name",
        year="Event year",
        start_at="Start time, ISO-8601 (e.g. 2026-09-01T18:00:00+00:00)",
        end_at="End time, ISO-8601",
        ctftime_event_id="CTFTime event ID, if this exists on CTFTime",
        ctftime_url="CTFTime event URL",
        official_url="Organizer/platform URL",
        weight="CTFTime weight, if known",
    )
    async def addctf(
        interaction: discord.Interaction,
        name: str,
        year: int,
        start_at: str,
        end_at: str,
        ctftime_event_id: int | None = None,
        ctftime_url: str | None = None,
        official_url: str | None = None,
        weight: float | None = None,
    ) -> None:
        try:
            parsed_start = parse_iso_datetime(start_at)
            parsed_end = parse_iso_datetime(end_at)
        except ValueError:
            await interaction.response.send_message(
                "start_at/end_at must be ISO-8601 timestamps.", ephemeral=True
            )
            return

        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        try:
            async with session_factory() as session, session.begin():
                ctf = await ctfs_service.create_draft(
                    session,
                    actor_discord_id=interaction.user.id,
                    name=name,
                    year=year,
                    start_at=parsed_start,
                    end_at=parsed_end,
                    ctftime_event_id=ctftime_event_id,
                    ctftime_url=ctftime_url,
                    official_url=official_url,
                    weight=weight,
                )
        except (ValueError, ctfs_service.DuplicateCTFTimeEventError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(
            f"Created draft CTF #{ctf.id}: {ctf.name} ({ctf.year})."
        )
