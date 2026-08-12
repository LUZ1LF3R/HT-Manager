from __future__ import annotations

import logging

import discord

logger = logging.getLogger(__name__)


class DiscordResourceError(Exception):
    """Raised when a Discord role/forum operation can't complete."""


async def _get_guild(bot: discord.Client, guild_id: int) -> discord.Guild:
    guild = bot.get_guild(guild_id)
    if guild is not None:
        return guild
    try:
        return await bot.fetch_guild(guild_id)
    except discord.HTTPException as exc:
        raise DiscordResourceError(f"Could not fetch guild {guild_id}") from exc


async def create_role(bot: discord.Client, *, guild_id: int, name: str) -> int:
    guild = await _get_guild(bot, guild_id)
    try:
        role = await guild.create_role(name=name, mentionable=True, reason="CTF workspace role")
    except discord.HTTPException as exc:
        raise DiscordResourceError(f"Could not create role {name!r}") from exc
    return role.id


async def _get_category(guild: discord.Guild, category_id: int) -> discord.CategoryChannel:
    channel = guild.get_channel(category_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(category_id)
        except discord.HTTPException as exc:
            raise DiscordResourceError(f"Could not fetch category {category_id}") from exc
    if not isinstance(channel, discord.CategoryChannel):
        raise DiscordResourceError(f"Channel {category_id} is not a category")
    return channel


async def create_ctf_forum(
    bot: discord.Client, *, guild_id: int, category_id: int, ctf_name: str
) -> int:
    """Creates a dedicated Forum channel for the CTF under `category_id`
    (spec §8). One forum per CTF, not a shared one — the CTF role exists
    for pinging/organization, not access control. Returns the forum
    channel's ID."""
    guild = await _get_guild(bot, guild_id)
    category = await _get_category(guild, category_id)
    try:
        forum = await guild.create_forum(
            name=ctf_name, category=category, reason="CTF workspace forum"
        )
    except discord.HTTPException as exc:
        raise DiscordResourceError(f"Could not create forum channel for {ctf_name!r}") from exc
    return forum.id


async def create_general_post(
    bot: discord.Client, *, guild_id: int, forum_channel_id: int, ctf_name: str
) -> int:
    """Creates the single starting "general" post inside a CTF's dedicated
    forum channel. Returns the created thread's ID."""
    guild = await _get_guild(bot, guild_id)
    channel = guild.get_channel(forum_channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(forum_channel_id)
        except discord.HTTPException as exc:
            raise DiscordResourceError(f"Could not fetch forum channel {forum_channel_id}") from exc
    if not isinstance(channel, discord.ForumChannel):
        raise DiscordResourceError(f"Channel {forum_channel_id} is not a forum channel")

    try:
        result = await channel.create_thread(
            name="general", content=f"Workspace for **{ctf_name}**. GLHF!"
        )
    except discord.HTTPException as exc:
        raise DiscordResourceError(f"Could not create general post for {ctf_name!r}") from exc
    return result.thread.id


async def move_forum_to_category(
    bot: discord.Client, *, guild_id: int, forum_channel_id: int, category_id: int
) -> None:
    """Moves a CTF's forum channel into `category_id` (spec §8's post-`/endctf`
    archive move). Logs and returns rather than raising — this runs from a
    batch job (spec §18.1), a single failure shouldn't abort the run."""
    guild = await _get_guild(bot, guild_id)
    channel = guild.get_channel(forum_channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(forum_channel_id)
        except discord.HTTPException:
            logger.warning(
                "Could not fetch forum channel %s to move to archive", forum_channel_id,
                exc_info=True,
            )
            return
    try:
        category = await _get_category(guild, category_id)
        await channel.edit(category=category, reason="CTF finished — moved to archive category")
    except (discord.HTTPException, DiscordResourceError):
        logger.warning(
            "Could not move forum channel %s to archive category %s",
            forum_channel_id, category_id, exc_info=True,
        )


async def assign_role(
    bot: discord.Client, *, guild_id: int, role_id: int, user_ids: list[int]
) -> None:
    guild = await _get_guild(bot, guild_id)
    role = guild.get_role(role_id)
    if role is None:
        raise DiscordResourceError(f"Role {role_id} not found in guild {guild_id}")

    for user_id in user_ids:
        try:
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            await member.add_roles(role, reason="CTF participant")
        except discord.HTTPException:
            logger.warning(
                "Could not assign role %s to user_id=%s", role_id, user_id, exc_info=True
            )


async def delete_role(bot: discord.Client, *, guild_id: int, role_id: int) -> None:
    guild = await _get_guild(bot, guild_id)
    role = guild.get_role(role_id)
    if role is None:
        return
    try:
        await role.delete(reason="CTF resource retention expired")
    except discord.HTTPException:
        logger.warning("Could not delete role %s", role_id, exc_info=True)


async def archive_workspace(bot: discord.Client, *, guild_id: int, thread_id: int) -> None:
    guild = await _get_guild(bot, guild_id)
    thread = guild.get_thread(thread_id)
    if thread is None:
        try:
            thread = await guild.fetch_channel(thread_id)
        except discord.HTTPException:
            logger.warning("Could not fetch thread %s for archiving", thread_id, exc_info=True)
            return
    try:
        await thread.edit(archived=True, locked=True, reason="CTF resource retention expired")
    except discord.HTTPException:
        logger.warning("Could not archive thread %s", thread_id, exc_info=True)
