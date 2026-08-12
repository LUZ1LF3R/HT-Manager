from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTFStatus
from ht_manager.db.models.ctf_discord_resource import CTFDiscordResource
from ht_manager.db.models.poll import Poll, PollOption, PollStatus, PollVote
from ht_manager.db.repositories import audit_log as audit_log_repo
from ht_manager.db.repositories import ctf_discord_resources as resources_repo
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import polls as polls_repo
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import discord_resources
from ht_manager.services import participation as participation_service

# Discord native polls allow at most 10 answers; leave headroom.
MAX_CANDIDATES = 8
DEFAULT_POLL_DURATION_HOURS = 48


class PollNotFoundError(Exception):
    pass


class InvalidPollStateError(Exception):
    pass


class NotEnoughCandidatesError(Exception):
    pass


async def open_draft(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    guild_id: int,
    channel_id: int,
    ctf_ids: list[int],
) -> Poll:
    if not ctf_ids:
        raise NotEnoughCandidatesError("No candidate CTFs to draft a poll from")

    poll = Poll(guild_id=guild_id, channel_id=channel_id, status=PollStatus.DRAFTING)
    await polls_repo.add_poll(session, poll)
    for index, ctf_id in enumerate(ctf_ids):
        await polls_repo.add_option(
            session, PollOption(poll_id=poll.id, ctf_id=ctf_id, option_index=index)
        )
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="poll_drafted",
        target_table="polls",
        target_id=poll.id,
        before=None,
        after={"ctf_ids": ctf_ids},
    )
    return poll


async def remove_candidate(
    session: AsyncSession, *, actor_discord_id: int, poll_id: int, ctf_id: int
) -> None:
    poll = await _get_drafting_poll(session, poll_id)
    options = await polls_repo.list_options(session, poll.id)
    match = next((option for option in options if option.ctf_id == ctf_id), None)
    if match is None:
        return
    await polls_repo.delete_option(session, match)
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="poll_candidate_removed",
        target_table="polls",
        target_id=poll.id,
        before={"ctf_id": ctf_id},
        after=None,
    )


async def add_candidate(
    session: AsyncSession, *, actor_discord_id: int, poll_id: int, ctf_id: int
) -> PollOption:
    poll = await _get_drafting_poll(session, poll_id)
    options = await polls_repo.list_options(session, poll.id)
    if any(option.ctf_id == ctf_id for option in options):
        raise ValueError(f"CTF {ctf_id} is already a candidate in poll {poll_id}")
    option = await polls_repo.add_option(
        session, PollOption(poll_id=poll.id, ctf_id=ctf_id, option_index=len(options))
    )
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="poll_candidate_added",
        target_table="polls",
        target_id=poll.id,
        before=None,
        after={"ctf_id": ctf_id},
    )
    return option


async def cancel_draft(session: AsyncSession, *, actor_discord_id: int, poll_id: int) -> None:
    poll = await _get_drafting_poll(session, poll_id)
    # poll_options has no ON DELETE CASCADE, so its rows must go first or
    # deleting the poll violates the foreign key. A DRAFTING poll never has
    # votes (those only exist from finalize() on an OPEN poll), so options
    # are the only child rows to clear.
    for option in await polls_repo.list_options(session, poll.id):
        await polls_repo.delete_option(session, option)
    await polls_repo.delete_poll(session, poll)
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="poll_draft_cancelled",
        target_table="polls",
        target_id=poll_id,
        before=None,
        after=None,
    )


async def publish(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    poll_id: int,
    discord_message_id: int,
    closes_at: datetime,
) -> Poll:
    poll = await _get_drafting_poll(session, poll_id)
    options = await polls_repo.list_options(session, poll.id)
    if len(options) < 2:
        raise NotEnoughCandidatesError("A poll needs at least two candidates to publish")

    poll.status = PollStatus.OPEN
    poll.discord_message_id = discord_message_id
    poll.closes_at = closes_at
    await session.flush()

    for option in options:
        ctf = await ctfs_repo.get(session, option.ctf_id)
        if ctf is not None:
            await ctfs_service.transition(
                session, actor_discord_id=actor_discord_id, ctf=ctf, new_status=CTFStatus.POLLING
            )

    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="poll_published",
        target_table="polls",
        target_id=poll.id,
        before=None,
        after={"discord_message_id": discord_message_id, "closes_at": closes_at.isoformat()},
    )
    return poll


async def finalize(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    poll_id: int,
    votes: dict[int, list[int]],
) -> Poll:
    """Tallies votes and closes the poll per spec §7.3: a single leader wins
    (`SELECTED`), a tie among leaders needs `/resolvepoll` (`TIED`), and zero
    total votes cancels the whole cycle without creating a workspace."""
    poll = await polls_repo.get(session, poll_id)
    if poll is None:
        raise PollNotFoundError(f"Poll {poll_id} not found")
    if poll.status is not PollStatus.OPEN:
        raise InvalidPollStateError(f"Poll {poll_id} is {poll.status.value}, not open")

    for ctf_id, voter_ids in votes.items():
        for discord_user_id in voter_ids:
            await polls_repo.add_vote(
                session, PollVote(poll_id=poll.id, ctf_id=ctf_id, discord_user_id=discord_user_id)
            )

    counts = {ctf_id: len(voter_ids) for ctf_id, voter_ids in votes.items()}
    total_votes = sum(counts.values())

    options = await polls_repo.list_options(session, poll.id)
    candidate_ctf_ids = [option.ctf_id for option in options]

    if total_votes == 0:
        for ctf_id in candidate_ctf_ids:
            await _cancel_candidate(session, actor_discord_id, ctf_id)
        poll.status = PollStatus.CANCELLED
    else:
        await _resolve_leaders(
            session,
            actor_discord_id=actor_discord_id,
            poll=poll,
            candidate_ctf_ids=candidate_ctf_ids,
            counts=counts,
        )

    await session.flush()
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="poll_finalized",
        target_table="polls",
        target_id=poll.id,
        before=None,
        after={"status": poll.status.value, "votes": counts, "winning_ctf_id": poll.winning_ctf_id},
    )
    return poll


async def _resolve_leaders(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    poll: Poll,
    candidate_ctf_ids: list[int],
    counts: dict[int, int],
) -> None:
    max_votes = max(counts.get(ctf_id, 0) for ctf_id in candidate_ctf_ids)
    leaders = [ctf_id for ctf_id in candidate_ctf_ids if counts.get(ctf_id, 0) == max_votes]

    for ctf_id in candidate_ctf_ids:
        if ctf_id not in leaders:
            await _cancel_candidate(session, actor_discord_id, ctf_id)

    if len(leaders) == 1:
        winner = leaders[0]
        await _transition_candidate(session, actor_discord_id, winner, CTFStatus.SELECTED)
        poll.status = PollStatus.CLOSED
        poll.winning_ctf_id = winner
    else:
        for ctf_id in leaders:
            await _transition_candidate(session, actor_discord_id, ctf_id, CTFStatus.TIED)
        poll.status = PollStatus.TIED


async def _transition_candidate(
    session: AsyncSession, actor_discord_id: int, ctf_id: int, new_status: CTFStatus
) -> None:
    ctf = await ctfs_repo.get(session, ctf_id)
    if ctf is not None:
        await ctfs_service.transition(
            session, actor_discord_id=actor_discord_id, ctf=ctf, new_status=new_status
        )


async def _cancel_candidate(session: AsyncSession, actor_discord_id: int, ctf_id: int) -> None:
    ctf = await ctfs_repo.get(session, ctf_id)
    if ctf is None or ctf.status is CTFStatus.CANCELLED:
        return
    await ctfs_service.transition(
        session, actor_discord_id=actor_discord_id, ctf=ctf, new_status=CTFStatus.CANCELLED
    )


async def _get_drafting_poll(session: AsyncSession, poll_id: int) -> Poll:
    poll = await polls_repo.get(session, poll_id)
    if poll is None:
        raise PollNotFoundError(f"Poll {poll_id} not found")
    if poll.status is not PollStatus.DRAFTING:
        raise InvalidPollStateError(f"Poll {poll_id} is {poll.status.value}, not drafting")
    return poll


async def resolve_tie(session: AsyncSession, *, actor_discord_id: int, ctf_id: int) -> Poll:
    """`/resolvepoll` (spec §16): an admin manually picks the winner among a
    `TIED` poll's leaders. Losing leaders are cancelled, same as a clean win."""
    ctf = await ctfs_repo.get(session, ctf_id)
    if ctf is None:
        raise ctfs_service.CTFNotFoundError(f"CTF {ctf_id} not found")
    if ctf.status is not CTFStatus.TIED:
        raise InvalidPollStateError(f"CTF {ctf_id} is {ctf.status.value}, not tied")

    poll = await polls_repo.get_poll_for_ctf(session, ctf_id)
    if poll is None or poll.status is not PollStatus.TIED:
        raise PollNotFoundError(f"No tied poll found for CTF {ctf_id}")

    options = await polls_repo.list_options(session, poll.id)
    for option in options:
        if option.ctf_id == ctf_id:
            continue
        await _cancel_candidate(session, actor_discord_id, option.ctf_id)

    await ctfs_service.transition(
        session, actor_discord_id=actor_discord_id, ctf=ctf, new_status=CTFStatus.SELECTED
    )
    poll.status = PollStatus.CLOSED
    poll.winning_ctf_id = ctf_id
    await session.flush()

    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="poll_tie_resolved",
        target_table="polls",
        target_id=poll.id,
        before=None,
        after={"winning_ctf_id": ctf_id},
    )
    return poll


async def setup_ctf_resources(
    session_factory,
    *,
    actor_discord_id: int,
    bot,
    ctf_id: int,
    guild_id: int,
    category_id: int,
    retention_days: int = 60,
) -> None:
    """The winner-resolution sequence (spec §15.2), triggered once by either
    a clean poll win or `/resolvepoll`. Each step commits independently and
    no transaction spans a Discord call, so on failure the CTF is left in
    its last successfully-reached state — safe to retry via `/setupctf`
    (every step below re-checks existing state before acting)."""
    async with session_factory() as session:
        ctf = await ctfs_repo.get(session, ctf_id)
    if ctf is None:
        raise ctfs_service.CTFNotFoundError(f"CTF {ctf_id} not found")
    if ctf.status is CTFStatus.ACTIVE:
        return
    if ctf.status is not CTFStatus.SELECTED:
        raise InvalidPollStateError(f"CTF {ctf_id} is {ctf.status.value}, not selected")

    async with session_factory() as session:
        resource = await resources_repo.get_by_ctf_id(session, ctf_id)

    role_id = resource.role_id if resource is not None else None
    forum_channel_id = resource.forum_channel_id if resource is not None else None
    thread_id = resource.thread_id if resource is not None else None
    cleanup_after = datetime.now(UTC) + timedelta(days=retention_days)

    # Each Discord object is persisted the moment it exists, before the next
    # one is created. Creating both and saving once would mean a failure in
    # between leaves a role that nothing records — invisible to cleanup, and
    # duplicated by the next /setupctf retry.
    if role_id is None:
        role_id = await discord_resources.create_role(
            bot, guild_id=guild_id, name=f"{ctf.name} {ctf.year}"
        )
        await _save_resource(
            session_factory, ctf_id=ctf_id, cleanup_after=cleanup_after, role_id=role_id
        )

    if forum_channel_id is None:
        forum_channel_id = await discord_resources.create_ctf_forum(
            bot, guild_id=guild_id, category_id=category_id, ctf_name=ctf.name
        )
        await _save_resource(
            session_factory,
            ctf_id=ctf_id,
            cleanup_after=cleanup_after,
            forum_channel_id=forum_channel_id,
        )

    if thread_id is None:
        thread_id = await discord_resources.create_general_post(
            bot, guild_id=guild_id, forum_channel_id=forum_channel_id, ctf_name=ctf.name
        )
        await _save_resource(
            session_factory, ctf_id=ctf_id, cleanup_after=cleanup_after, thread_id=thread_id
        )

    async with session_factory() as session, session.begin():
        voter_ids = await polls_repo.list_voter_ids_for_ctf(session, ctf_id)
        for voter_id in voter_ids:
            await participation_service.record_from_vote(
                session, ctf_id=ctf_id, discord_user_id=voter_id
            )

    await discord_resources.assign_role(bot, guild_id=guild_id, role_id=role_id, user_ids=voter_ids)

    async with session_factory() as session, session.begin():
        ctf = await ctfs_repo.get(session, ctf_id)
        if ctf is None:
            raise ctfs_service.CTFNotFoundError(f"CTF {ctf_id} not found")
        await ctfs_service.transition(
            session, actor_discord_id=actor_discord_id, ctf=ctf, new_status=CTFStatus.ACTIVE
        )


async def _save_resource(
    session_factory,
    *,
    ctf_id: int,
    cleanup_after: datetime,
    role_id: int | None = None,
    forum_channel_id: int | None = None,
    thread_id: int | None = None,
) -> None:
    """Checkpoints one just-created Discord object onto the CTF's resource row.

    Only writes the field it was handed, so the role/forum/post steps can
    each checkpoint independently on a partial run. `cleanup_after` is
    stamped once and never moved (spec §8) — a retry must not extend the
    retention window.
    """
    async with session_factory() as session, session.begin():
        resource = await resources_repo.get_by_ctf_id(session, ctf_id)
        if resource is None:
            await resources_repo.add(
                session,
                CTFDiscordResource(
                    ctf_id=ctf_id,
                    role_id=role_id,
                    forum_channel_id=forum_channel_id,
                    thread_id=thread_id,
                    cleanup_after=cleanup_after,
                ),
            )
            return

        if role_id is not None:
            resource.role_id = role_id
        if forum_channel_id is not None:
            resource.forum_channel_id = forum_channel_id
        if thread_id is not None:
            resource.thread_id = thread_id
        if resource.cleanup_after is None:
            resource.cleanup_after = cleanup_after
