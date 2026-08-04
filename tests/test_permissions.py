from unittest.mock import MagicMock

import discord

from ht_manager.bot.permissions import admin_only, is_admin
from ht_manager.config import Settings


def _interaction_with_role_ids(role_ids: list[int], guild_id: int = 123) -> discord.Interaction:
    member = MagicMock(spec=discord.Member)
    member.roles = [MagicMock(spec=discord.Role, id=role_id) for role_id in role_ids]
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = member
    interaction.guild_id = guild_id
    return interaction


def test_is_admin_true_when_member_has_admin_role(settings: Settings) -> None:
    interaction = _interaction_with_role_ids([1, 999])

    assert is_admin(interaction, settings) is True


def test_is_admin_false_when_member_lacks_admin_role(settings: Settings) -> None:
    interaction = _interaction_with_role_ids([999])

    assert is_admin(interaction, settings) is False


def test_is_admin_false_when_user_is_not_a_member(settings: Settings) -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.User)
    interaction.guild_id = 123

    assert is_admin(interaction, settings) is False


def test_is_admin_false_when_guild_id_does_not_match(settings: Settings) -> None:
    interaction = _interaction_with_role_ids([1], guild_id=999)

    assert is_admin(interaction, settings) is False


async def test_admin_only_check_predicate_matches_is_admin(settings: Settings) -> None:
    interaction = _interaction_with_role_ids([1])
    interaction.client = MagicMock()
    interaction.client.settings = settings

    async def dummy() -> None:
        pass

    decorated = admin_only()(dummy)
    checks = decorated.__discord_app_commands_checks__

    assert len(checks) == 1
    assert await checks[0](interaction) is True
