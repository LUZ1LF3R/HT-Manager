from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.participation import ParticipationSource
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import participation as participation_service

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 3, tzinfo=UTC)


async def _make_ctf(session: AsyncSession) -> int:
    ctf = await ctfs_service.create_draft(
        session, actor_discord_id=1, name="A", year=2026, start_at=START, end_at=END
    )
    return ctf.id


async def test_add_participation_persists(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    participation = await participation_service.add_participation(
        db_session, actor_discord_id=1, ctf_id=ctf_id, discord_user_id=100
    )
    assert participation.source is ParticipationSource.MANUAL


async def test_add_participation_rejects_duplicate(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    await participation_service.add_participation(
        db_session, actor_discord_id=1, ctf_id=ctf_id, discord_user_id=100
    )
    with pytest.raises(participation_service.DuplicateParticipationError):
        await participation_service.add_participation(
            db_session, actor_discord_id=1, ctf_id=ctf_id, discord_user_id=100
        )


async def test_add_participation_rejects_unknown_ctf(db_session: AsyncSession) -> None:
    """Without this check, the insert falls through to participations'
    foreign key and raises an unhandled IntegrityError instead of a clean,
    catchable error — inconsistent with results_service.add_result and
    summary_service.set_category_stat, which both check this first."""
    with pytest.raises(participation_service.CTFNotFoundError):
        await participation_service.add_participation(
            db_session, actor_discord_id=1, ctf_id=999_999, discord_user_id=100
        )


async def test_record_from_vote_is_idempotent(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    await participation_service.record_from_vote(db_session, ctf_id=ctf_id, discord_user_id=100)
    await participation_service.record_from_vote(db_session, ctf_id=ctf_id, discord_user_id=100)

    from ht_manager.db.repositories import participation as participation_repo

    rows = await participation_repo.list_for_ctf(db_session, ctf_id)
    assert len(rows) == 1
    assert rows[0].source is ParticipationSource.VOTE


async def test_remove_participation_deletes_row(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    await participation_service.add_participation(
        db_session, actor_discord_id=1, ctf_id=ctf_id, discord_user_id=100
    )
    await participation_service.remove_participation(
        db_session, actor_discord_id=1, ctf_id=ctf_id, discord_user_id=100
    )

    from ht_manager.db.repositories import participation as participation_repo

    assert await participation_repo.get(db_session, ctf_id=ctf_id, discord_user_id=100) is None


async def test_remove_participation_raises_when_missing(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    with pytest.raises(participation_service.ParticipationNotFoundError):
        await participation_service.remove_participation(
            db_session, actor_discord_id=1, ctf_id=ctf_id, discord_user_id=100
        )
