from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTFStatus
from ht_manager.db.models.ctf_discord_resource import CTFDiscordResource
from ht_manager.db.repositories import ctf_discord_resources as resources_repo
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import participation as participation_service
from ht_manager.services import results as results_service
from ht_manager.services import summary as summary_service

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 3, tzinfo=UTC)


async def _make_active_ctf(session: AsyncSession) -> int:
    ctf = await ctfs_service.create_draft(
        session, actor_discord_id=1, name="L3akCTF", year=2026, start_at=START, end_at=END
    )
    await ctfs_service.transition(
        session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.POLLING
    )
    await ctfs_service.transition(
        session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.SELECTED
    )
    await ctfs_service.transition(session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.ACTIVE)
    return ctf.id


async def test_set_category_stat_creates_then_updates(db_session: AsyncSession) -> None:
    ctf_id = await _make_active_ctf(db_session)
    await summary_service.set_category_stat(
        db_session, actor_discord_id=1, ctf_id=ctf_id, category_name="Web", solved=8, total=8
    )
    stat = await summary_service.set_category_stat(
        db_session, actor_discord_id=1, ctf_id=ctf_id, category_name="Web", solved=7, total=8
    )
    assert stat.solved == 7
    assert stat.total == 8


async def test_set_category_stat_rejects_unknown_ctf(db_session: AsyncSession) -> None:
    with pytest.raises(summary_service.CTFNotFoundError):
        await summary_service.set_category_stat(
            db_session, actor_discord_id=1, ctf_id=999_999, category_name="Web", solved=1, total=1
        )


async def test_finish_ctf_transitions_and_renders_summary(db_session: AsyncSession) -> None:
    ctf_id = await _make_active_ctf(db_session)
    await summary_service.set_category_stat(
        db_session, actor_discord_id=1, ctf_id=ctf_id, category_name="Web", solved=8, total=8
    )
    await summary_service.set_category_stat(
        db_session, actor_discord_id=1, ctf_id=ctf_id, category_name="Pwn", solved=5, total=9
    )
    await results_service.add_result(
        db_session, actor_discord_id=1, ctf_id=ctf_id, placement=47, total_teams=1000
    )
    await participation_service.add_participation(
        db_session, actor_discord_id=1, ctf_id=ctf_id, discord_user_id=100
    )

    summary = await summary_service.finish_ctf(db_session, actor_discord_id=1, ctf_id=ctf_id)

    assert "Finished" in summary
    assert "Placement: 47 / 1000" in summary
    assert "Web  8/8" in summary or "Web 8/8" in summary
    assert "Total solved: 13/17" in summary
    assert "Participants: 1" in summary

    ctf = await ctfs_repo.get(db_session, ctf_id)
    assert ctf.status is CTFStatus.FINISHED


async def test_finish_ctf_schedules_workspace_archive_move(db_session: AsyncSession) -> None:
    ctf_id = await _make_active_ctf(db_session)
    await resources_repo.add(
        db_session, CTFDiscordResource(ctf_id=ctf_id, role_id=1, forum_channel_id=2, thread_id=3)
    )

    await summary_service.finish_ctf(db_session, actor_discord_id=1, ctf_id=ctf_id)

    resource = await resources_repo.get_by_ctf_id(db_session, ctf_id)
    assert resource.archive_after is not None
    expected = datetime.now(UTC) + timedelta(days=summary_service.WORKSPACE_ARCHIVE_DELAY_DAYS)
    assert abs((resource.archive_after - expected).total_seconds()) < 60


async def test_finish_ctf_rejects_invalid_transition(db_session: AsyncSession) -> None:
    ctf = await ctfs_service.create_draft(
        db_session, actor_discord_id=1, name="Draft", year=2026, start_at=START, end_at=END
    )
    with pytest.raises(ctfs_service.InvalidCTFTransitionError):
        await summary_service.finish_ctf(db_session, actor_discord_id=1, ctf_id=ctf.id)


async def test_render_summary_omits_solves_section_without_stats(db_session: AsyncSession) -> None:
    ctf_id = await _make_active_ctf(db_session)
    summary = await summary_service.render_summary(db_session, ctf_id)
    assert "Solves" not in summary
    assert "Participants: 0" in summary


async def test_set_category_stat_blocked_once_archived(db_session: AsyncSession) -> None:
    """Same lock as /editctf — an archived CTF's record is history."""
    ctf_id = await _make_active_ctf(db_session)
    ctf = await ctfs_repo.get(db_session, ctf_id)
    await ctfs_service.transition(
        db_session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.FINISHED
    )
    await ctfs_service.transition(
        db_session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.ARCHIVED
    )

    with pytest.raises(ctfs_service.InvalidCTFStateError):
        await summary_service.set_category_stat(
            db_session, actor_discord_id=1, ctf_id=ctf_id, category_name="Web", solved=1, total=1
        )


async def test_render_summary_shows_score_from_a_synced_result(db_session: AsyncSession) -> None:
    """The summary's `Score:` line (spec §12) comes from `score`, which is
    where the CTFTime sync stores that event's points."""
    ctf_id = await _make_active_ctf(db_session)
    await results_service.upsert_from_ctftime(
        db_session,
        actor_discord_id=999,
        ctf_id=ctf_id,
        placement=47,
        total_teams=1000,
        score=8214.0,
        source_url=None,
    )

    summary = await summary_service.render_summary(db_session, ctf_id)

    assert "Placement: 47 / 1000" in summary
    assert "Score: 8214" in summary
