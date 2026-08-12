from __future__ import annotations

from datetime import UTC, datetime, timedelta

import discord
from discord.ext.commands import Bot

from ht_manager.bot.permissions import admin_only
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import polls as polls_service
from ht_manager.services.ctftime import CTFTimeClient, CTFTimeError

DEFAULT_WINDOW_DAYS = 7


def _build_embed(candidates: dict[int, str]) -> discord.Embed:
    embed = discord.Embed(
        title="Next CTF — Draft",
        description="Remove any CTFs that shouldn't be on the ballot, then Publish Poll.",
        color=discord.Color.blurple(),
    )
    value = "\n".join(f"- {name}" for name in candidates.values()) if candidates else "(none left)"
    embed.add_field(name="Candidates", value=value, inline=False)
    return embed


class RemoveCandidateSelect(discord.ui.Select):
    def __init__(self, view: NextCtfDraftView) -> None:
        options = [
            discord.SelectOption(label=name[:100], value=str(ctf_id))
            for ctf_id, name in view.candidates.items()
        ]
        super().__init__(placeholder="Remove a CTF from the draft...", options=options)
        self.draft_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.draft_view
        if interaction.user.id != view.admin_id:
            await interaction.response.send_message(
                "Only the admin who started this draft can edit it.", ephemeral=True
            )
            return

        ctf_id = int(self.values[0])
        async with view.session_factory() as session, session.begin():
            await polls_service.remove_candidate(
                session, actor_discord_id=interaction.user.id, poll_id=view.poll_id, ctf_id=ctf_id
            )
        view.candidates.pop(ctf_id, None)
        view.rebuild_items()
        await interaction.response.edit_message(embed=_build_embed(view.candidates), view=view)


class PublishButton(discord.ui.Button):
    def __init__(self, view: NextCtfDraftView) -> None:
        super().__init__(label="Publish Poll", style=discord.ButtonStyle.green)
        self.draft_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.draft_view
        if interaction.user.id != view.admin_id:
            await interaction.response.send_message(
                "Only the admin who started this draft can edit it.", ephemeral=True
            )
            return
        if len(view.candidates) < 2:
            await interaction.response.send_message(
                "Need at least two candidates to publish a poll.", ephemeral=True
            )
            return

        await interaction.response.defer()
        poll_message = discord.Poll(
            question="Vote for the next CTF!",
            duration=timedelta(hours=polls_service.DEFAULT_POLL_DURATION_HOURS),
        )
        for name in view.candidates.values():
            poll_message.add_answer(text=name[:55])

        message = await interaction.channel.send(poll=poll_message)
        closes_at = datetime.now(UTC) + timedelta(hours=polls_service.DEFAULT_POLL_DURATION_HOURS)

        async with view.session_factory() as session, session.begin():
            await polls_service.publish(
                session,
                actor_discord_id=interaction.user.id,
                poll_id=view.poll_id,
                discord_message_id=message.id,
                closes_at=closes_at,
            )

        view.stop()
        await interaction.edit_original_response(
            content="Poll published! Votes close in "
            f"{polls_service.DEFAULT_POLL_DURATION_HOURS}h.",
            embed=None,
            view=None,
        )


class CancelButton(discord.ui.Button):
    def __init__(self, view: NextCtfDraftView) -> None:
        super().__init__(label="Cancel Draft", style=discord.ButtonStyle.red)
        self.draft_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.draft_view
        if interaction.user.id != view.admin_id:
            await interaction.response.send_message(
                "Only the admin who started this draft can edit it.", ephemeral=True
            )
            return

        async with view.session_factory() as session, session.begin():
            await polls_service.cancel_draft(
                session, actor_discord_id=interaction.user.id, poll_id=view.poll_id
            )
        view.stop()
        await interaction.response.edit_message(content="Draft cancelled.", embed=None, view=None)


class NextCtfDraftView(discord.ui.View):
    def __init__(
        self, *, poll_id: int, candidates: dict[int, str], admin_id: int, session_factory
    ) -> None:
        super().__init__(timeout=900)
        self.poll_id = poll_id
        self.candidates = candidates
        self.admin_id = admin_id
        self.session_factory = session_factory
        self.rebuild_items()

    def rebuild_items(self) -> None:
        self.clear_items()
        if self.candidates:
            self.add_item(RemoveCandidateSelect(self))
        self.add_item(PublishButton(self))
        self.add_item(CancelButton(self))


def register_nextctf_command(bot: Bot) -> None:
    @bot.tree.command(
        name="nextctf", description="Fetch and curate upcoming CTFs, then start a poll"
    )
    @admin_only()
    @discord.app_commands.describe(window_days="How many days ahead to look on CTFTime")
    async def nextctf(
        interaction: discord.Interaction, window_days: int = DEFAULT_WINDOW_DAYS
    ) -> None:
        await interaction.response.defer()
        session_factory = interaction.client.session_factory  # type: ignore[attr-defined]

        async with session_factory() as session:
            non_terminal = await ctfs_repo.list_non_terminal(session)
        if non_terminal:
            names = ", ".join(f"{ctf.name} ({ctf.status.value})" for ctf in non_terminal)
            await interaction.followup.send(
                "A CTF is already in progress: "
                f"{names}. Use /endctf or /archivectf before starting another.",
            )
            return

        client = CTFTimeClient()
        try:
            events = await client.list_upcoming_events(
                start=datetime.now(UTC),
                finish=datetime.now(UTC) + timedelta(days=window_days),
                limit=polls_service.MAX_CANDIDATES,
            )
        except CTFTimeError:
            await interaction.followup.send(
                "Couldn't reach CTFTime right now. Try again shortly, or use /addctf manually."
            )
            return
        finally:
            await client.aclose()

        if not events:
            await interaction.followup.send(
                "No upcoming CTFs found on CTFTime in that window. Use /addctf to add one manually."
            )
            return

        async with session_factory() as session, session.begin():
            candidates: dict[int, str] = {}
            for event in events:
                ctf = await ctfs_service.get_or_create_from_ctftime(
                    session, actor_discord_id=interaction.user.id, event=event
                )
                candidates[ctf.id] = ctf.name
            poll = await polls_service.open_draft(
                session,
                actor_discord_id=interaction.user.id,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                ctf_ids=list(candidates.keys()),
            )
            poll_id = poll.id

        view = NextCtfDraftView(
            poll_id=poll_id,
            candidates=candidates,
            admin_id=interaction.user.id,
            session_factory=session_factory,
        )
        await interaction.followup.send(embed=_build_embed(candidates), view=view)
