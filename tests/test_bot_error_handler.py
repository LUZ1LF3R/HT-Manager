from unittest.mock import AsyncMock, MagicMock

import discord
from discord import app_commands

from ht_manager.bot.client import HTManagerBot
from ht_manager.bot.permissions import admin_only
from ht_manager.config import Settings


def _interaction(response_done: bool = False) -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member, id=42)
    interaction.command = MagicMock(name="somecommand")
    interaction.response = MagicMock(spec=discord.InteractionResponse)
    interaction.response.is_done.return_value = response_done
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def test_admin_only_check_predicate_false_for_non_admin(settings: Settings) -> None:
    interaction = _interaction()
    interaction.user.roles = [MagicMock(spec=discord.Role, id=999)]
    interaction.guild_id = settings.discord_guild_id
    interaction.client = MagicMock()
    interaction.client.settings = settings

    async def dummy() -> None:
        pass

    decorated = admin_only()(dummy)
    checks = decorated.__discord_app_commands_checks__

    assert await checks[0](interaction) is False


async def test_on_app_command_error_check_failure_sends_denial_message(bot: HTManagerBot) -> None:
    interaction = _interaction(response_done=False)

    await bot._on_app_command_error(interaction, app_commands.CheckFailure("denied"))

    interaction.response.send_message.assert_awaited_once()
    message = interaction.response.send_message.call_args.args[0]
    assert "permission" in message.lower()


async def test_on_app_command_error_generic_error_sends_generic_message(bot: HTManagerBot) -> None:
    interaction = _interaction(response_done=False)

    await bot._on_app_command_error(interaction, app_commands.CommandInvokeError(
        MagicMock(), ValueError("boom")
    ))

    interaction.response.send_message.assert_awaited_once()
    message = interaction.response.send_message.call_args.args[0]
    assert "went wrong" in message.lower()


async def test_on_app_command_error_uses_followup_when_response_done(bot: HTManagerBot) -> None:
    interaction = _interaction(response_done=True)

    await bot._on_app_command_error(interaction, app_commands.CheckFailure("denied"))

    interaction.followup.send.assert_awaited_once()
    interaction.response.send_message.assert_not_awaited()


async def test_on_app_command_error_swallows_http_exception_from_reply(bot: HTManagerBot) -> None:
    interaction = _interaction(response_done=False)
    interaction.response.send_message = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(status=400), "bad")
    )

    await bot._on_app_command_error(interaction, app_commands.CheckFailure("denied"))
