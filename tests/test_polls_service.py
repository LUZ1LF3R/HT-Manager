from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTFStatus
from ht_manager.db.models.poll import PollStatus
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import polls as polls_repo
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import polls as polls_service

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 3, tzinfo=UTC)


async def _make_ctf(session: AsyncSession, name: str) -> int:
    ctf = await ctfs_service.create_draft(
        session, actor_discord_id=1, name=name, year=2026, start_at=START, end_at=END
    )
    return ctf.id


async def test_open_draft_creates_poll_and_options(db_session: AsyncSession) -> None:
    ctf_a = await _make_ctf(db_session, "A")
    ctf_b = await _make_ctf(db_session, "B")
    poll = await polls_service.open_draft(
        db_session, actor_discord_id=1, guild_id=1, channel_id=2, ctf_ids=[ctf_a, ctf_b]
    )
    assert poll.status is PollStatus.DRAFTING
    options = await polls_repo.list_options(db_session, poll.id)
    assert {o.ctf_id for o in options} == {ctf_a, ctf_b}


async def test_open_draft_requires_candidates(db_session: AsyncSession) -> None:
    with pytest.raises(polls_service.NotEnoughCandidatesError):
        await polls_service.open_draft(
            db_session, actor_discord_id=1, guild_id=1, channel_id=2, ctf_ids=[]
        )


async def test_remove_candidate_deletes_option(db_session: AsyncSession) -> None:
    ctf_a = await _make_ctf(db_session, "A")
    ctf_b = await _make_ctf(db_session, "B")
    poll = await polls_service.open_draft(
        db_session, actor_discord_id=1, guild_id=1, channel_id=2, ctf_ids=[ctf_a, ctf_b]
    )
    await polls_service.remove_candidate(
        db_session, actor_discord_id=1, poll_id=poll.id, ctf_id=ctf_a
    )
    options = await polls_repo.list_options(db_session, poll.id)
    assert {o.ctf_id for o in options} == {ctf_b}


async def test_publish_requires_two_candidates(db_session: AsyncSession) -> None:
    ctf_a = await _make_ctf(db_session, "A")
    poll = await polls_service.open_draft(
        db_session, actor_discord_id=1, guild_id=1, channel_id=2, ctf_ids=[ctf_a]
    )
    with pytest.raises(polls_service.NotEnoughCandidatesError):
        await polls_service.publish(
            db_session,
            actor_discord_id=1,
            poll_id=poll.id,
            discord_message_id=999,
            closes_at=datetime.now(UTC) + timedelta(hours=1),
        )


async def test_publish_transitions_candidates_to_polling(db_session: AsyncSession) -> None:
    ctf_a = await _make_ctf(db_session, "A")
    ctf_b = await _make_ctf(db_session, "B")
    poll = await polls_service.open_draft(
        db_session, actor_discord_id=1, guild_id=1, channel_id=2, ctf_ids=[ctf_a, ctf_b]
    )
    await polls_service.publish(
        db_session,
        actor_discord_id=1,
        poll_id=poll.id,
        discord_message_id=999,
        closes_at=datetime.now(UTC) + timedelta(hours=1),
    )
    ctf = await ctfs_repo.get(db_session, ctf_a)
    assert ctf.status is CTFStatus.POLLING


async def _open_and_publish(session: AsyncSession, names: list[str]) -> tuple[int, list[int]]:
    ctf_ids = [await _make_ctf(session, name) for name in names]
    poll = await polls_service.open_draft(
        session, actor_discord_id=1, guild_id=1, channel_id=2, ctf_ids=ctf_ids
    )
    await polls_service.publish(
        session,
        actor_discord_id=1,
        poll_id=poll.id,
        discord_message_id=999,
        closes_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return poll.id, ctf_ids


async def test_finalize_declares_clear_winner(db_session: AsyncSession) -> None:
    poll_id, (a, b) = await _open_and_publish(db_session, ["A", "B"])
    poll = await polls_service.finalize(
        db_session, actor_discord_id=1, poll_id=poll_id, votes={a: [10, 11], b: [12]}
    )
    assert poll.status is PollStatus.CLOSED
    assert poll.winning_ctf_id == a

    assert (await ctfs_repo.get(db_session, a)).status is CTFStatus.SELECTED
    assert (await ctfs_repo.get(db_session, b)).status is CTFStatus.CANCELLED


async def test_finalize_handles_tie(db_session: AsyncSession) -> None:
    poll_id, (a, b) = await _open_and_publish(db_session, ["A", "B"])
    poll = await polls_service.finalize(
        db_session, actor_discord_id=1, poll_id=poll_id, votes={a: [10], b: [11]}
    )
    assert poll.status is PollStatus.TIED
    assert poll.winning_ctf_id is None

    assert (await ctfs_repo.get(db_session, a)).status is CTFStatus.TIED
    assert (await ctfs_repo.get(db_session, b)).status is CTFStatus.TIED


async def test_finalize_handles_zero_votes(db_session: AsyncSession) -> None:
    poll_id, (a, b) = await _open_and_publish(db_session, ["A", "B"])
    poll = await polls_service.finalize(
        db_session, actor_discord_id=1, poll_id=poll_id, votes={a: [], b: []}
    )
    assert poll.status is PollStatus.CANCELLED

    assert (await ctfs_repo.get(db_session, a)).status is CTFStatus.CANCELLED
    assert (await ctfs_repo.get(db_session, b)).status is CTFStatus.CANCELLED


async def test_finalize_rejects_non_open_poll(db_session: AsyncSession) -> None:
    poll_id, (a, b) = await _open_and_publish(db_session, ["A", "B"])
    await polls_service.finalize(db_session, actor_discord_id=1, poll_id=poll_id, votes={a: [1]})
    with pytest.raises(polls_service.InvalidPollStateError):
        await polls_service.finalize(
            db_session, actor_discord_id=1, poll_id=poll_id, votes={a: [1]}
        )
