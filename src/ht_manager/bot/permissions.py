from __future__ import annotations

from collections.abc import Callable

import discord
from discord import app_commands

from ht_manager.config import Settings


def is_admin(interaction: discord.Interaction, settings: Settings) -> bool:
    """Server-side admin check for privileged commands (spec §6)."""
    if interaction.guild_id != settings.discord_guild_id:
        return False
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    member_role_ids = {role.id for role in member.roles}
    return any(role_id in member_role_ids for role_id in settings.admin_role_ids)


def admin_only() -> Callable[[app_commands.Command], app_commands.Command]:
    """Decorator for privileged commands: raises `app_commands.CheckFailure`
    (handled by `HTManagerBot._on_app_command_error`) instead of relying on
    each handler to call `is_admin` and reply on denial itself."""

    async def predicate(interaction: discord.Interaction) -> bool:
        settings: Settings = interaction.client.settings  # type: ignore[attr-defined]
        return is_admin(interaction, settings)

    return app_commands.check(predicate)
