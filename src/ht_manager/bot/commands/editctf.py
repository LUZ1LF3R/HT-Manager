from __future__ import annotations

from typing import Any

import discord
from discord.ext.commands import Bot

from ht_manager.bot.commands.addctf import parse_iso_datetime
from ht_manager.bot.permissions import admin_only
from ht_manager.services import ctfs as ctfs_service


def _collect_changes(
    *,
    name: str | None,
    year: int | None,
    start_at: str | None,
    end_at: str | None,
    ctftime_event_id: int | None,
    ctftime_url: str | None,
    official_url: str | None,
    weight: float | None,
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if name is not None:
        changes["name"] = name
    if year is not None:
        changes["year"] = year
    if ctftime_event_id is not None:
        changes["ctftime_event_id"] = ctftime_event_id
    if ctftime_url is not None:
        changes["ctftime_url"] = ctftime_url
    if official_url is not None:
        changes["official_url"] = official_url
    if weight is not None:
        changes["weight"] = weight
    if start_at is not None:
        changes["start_at"] = parse_iso_datetime(start_at)
    if end_at is not None:
        changes["end_at"] = parse_iso_datetime(end_at)
    return changes


def register_editctf_command(bot: Bot) -> None:
    @bot.tree.command(name="editctf", description="Correct a CTF's metadata")
    @admin_only()
    @discord.app_commands.describe(
        ctf_id="ID of the CTF to edit",
        name="Display/event name",
        year="Event year",
        start_at="Start time, ISO-8601",
        end_at="End time, ISO-8601",
        ctftime_event_id="CTFTime event ID",
        ctftime_url="CTFTime event URL",
        official_url="Organizer/platform URL",
        weight="CTFTime weight",
    )
    async def editctf(
        interaction: discord.Interaction,
        ctf_id: int,
        name: str | None = None,
        year: int | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        ctftime_event_id: int | None = None,
        ctftime_url: str | None = None,
        official_url: str | None = None,
        weight: float | None = None,
    ) -> None:
        try:
            changes = _collect_changes(
                name=name,
                year=year,
                start_at=start_at,
                end_at=end_at,
                ctftime_event_id=ctftime_event_id,
                ctftime_url=ctftime_url,
                official_url=official_url,
                weight=weight,
            )
        except ValueError:
            await interaction.response.send_message(
                "start_at/end_at must be ISO-8601 timestamps.", ephemeral=True
            )
            return

        if not changes:
            await interaction.response.send_message("No fields provided to update.", ephemeral=True)
            return

        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]
        try:
            async with session_factory() as session, session.begin():
                ctf = await ctfs_service.update_ctf(
                    session,
                    actor_discord_id=interaction.user.id,
                    ctf_id=ctf_id,
                    **changes,
                )
        except ctfs_service.CTFNotFoundError:
            await interaction.response.send_message(f"No CTF with ID {ctf_id}.", ephemeral=True)
            return
        except (
            ctfs_service.InvalidCTFStateError,
            ctfs_service.DuplicateCTFTimeEventError,
            ValueError,
        ) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(f"Updated CTF #{ctf.id}: {ctf.name}.")
