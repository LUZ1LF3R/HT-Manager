from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTFStatus
from ht_manager.db.models.poll import Poll, PollOption, PollStatus, PollVote
from ht_manager.db.repositories import audit_log as audit_log_repo
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import polls as polls_repo
from ht_manager.services import ctfs as ctfs_service

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
