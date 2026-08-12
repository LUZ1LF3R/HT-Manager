from __future__ import annotations

import logging

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import polls as polls_service

logger = logging.getLogger(__name__)


def register_setupctf_command(bot: Bot) -> None:
    @bot.tree.command(
        name="setupctf", description="Retry role/workspace creation for a selected CTF"
    )
    @admin_only()
    @discord.app_commands.describe(ctf_id="ID of the CTF to set up")
    async def setupctf(interaction: discord.Interaction, ctf_id: int) -> None:
        await interaction.response.defer()
        client = interaction.client
        settings = client.settings  # type: ignore[attr-defined]

        try:
            await polls_service.setup_ctf_resources(
                client.session_factory,  # type: ignore[attr-defined]
                actor_discord_id=interaction.user.id,
                bot=client,
                ctf_id=ctf_id,
                guild_id=settings.discord_guild_id,
                category_id=settings.ctf_category_id,
                retention_days=settings.ctf_resource_retention_days,
            )
        except ctfs_service.CTFNotFoundError as exc:
            await interaction.followup.send(str(exc))
            return
        except polls_service.InvalidPollStateError as exc:
            await interaction.followup.send(str(exc))
            return
        except Exception:
            logger.exception("Manual setup retry failed for ctf_id=%s", ctf_id)
            await interaction.followup.send(
                "Setup failed again — check the logs. It's safe to retry once the underlying "
                "issue (permissions, missing channel, etc.) is fixed."
            )
            return

        await interaction.followup.send(f"CTF #{ctf_id} is set up and active.")
