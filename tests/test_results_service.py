from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.result import ResultSource
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import results as results_service

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 3, tzinfo=UTC)


async def _make_ctf(session: AsyncSession) -> int:
    ctf = await ctfs_service.create_draft(
        session, actor_discord_id=1, name="A", year=2026, start_at=START, end_at=END
    )
    return ctf.id


async def _sync(
    session: AsyncSession,
    ctf_id: int,
    *,
    placement: int,
    total_teams: int | None = None,
    score: float | None = None,
):
    return await results_service.upsert_from_ctftime(
        session,
        actor_discord_id=999,
        ctf_id=ctf_id,
        placement=placement,
        total_teams=total_teams,
        score=score,
        source_url=None,
    )


async def test_add_result_persists_manual_source(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    result = await results_service.add_result(
        db_session, actor_discord_id=1, ctf_id=ctf_id, placement=3, total_teams=100
    )
    assert result.source is ResultSource.MANUAL
    assert result.placement == 3


async def test_add_result_rejects_unknown_ctf(db_session: AsyncSession) -> None:
    with pytest.raises(results_service.CTFNotFoundError):
        await results_service.add_result(db_session, actor_discord_id=1, ctf_id=999_999)


async def test_add_result_rejects_duplicate(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    await results_service.add_result(db_session, actor_discord_id=1, ctf_id=ctf_id, placement=3)
    with pytest.raises(results_service.DuplicateResultError):
        await results_service.add_result(db_session, actor_discord_id=1, ctf_id=ctf_id, placement=4)


async def test_edit_result_updates_fields_and_marks_manual(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    await _sync(db_session, ctf_id, placement=5, total_teams=50, score=1.2)
    result = await results_service.edit_result(
        db_session, actor_discord_id=1, ctf_id=ctf_id, placement=2
    )
    assert result.placement == 2
    assert result.source is ResultSource.MANUAL


async def test_edit_result_raises_when_missing(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    with pytest.raises(results_service.ResultNotFoundError):
        await results_service.edit_result(
            db_session, actor_discord_id=1, ctf_id=ctf_id, placement=2
        )


async def test_upsert_from_ctftime_creates_then_skips_unchanged(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    result, changed = await _sync(db_session, ctf_id, placement=1, total_teams=10, score=5.0)
    assert changed is True
    assert result.source is ResultSource.CTFTIME

    result, changed = await _sync(db_session, ctf_id, placement=1, total_teams=10, score=5.0)
    assert changed is False


async def test_upsert_from_ctftime_reports_change_on_new_placement(
    db_session: AsyncSession,
) -> None:
    ctf_id = await _make_ctf(db_session)
    await _sync(db_session, ctf_id, placement=3, total_teams=10, score=5.0)
    result, changed = await _sync(db_session, ctf_id, placement=2, total_teams=10, score=5.5)
    assert changed is True
    assert result.placement == 2


async def test_upsert_from_ctftime_stores_points_as_score(db_session: AsyncSession) -> None:
    """CTFTime's per-event `points` is the event score shown in the summary
    (spec §12), not the team's global rating points."""
    ctf_id = await _make_ctf(db_session)
    result, _ = await _sync(db_session, ctf_id, placement=47, total_teams=1000, score=8214.0)
    assert result.score == 8214.0
    assert result.rating_points is None


async def test_upsert_from_ctftime_never_overwrites_a_manual_result(
    db_session: AsyncSession,
) -> None:
    """An admin's /editresult correction is the last word — the 12-hour sync
    must not silently revert it."""
    ctf_id = await _make_ctf(db_session)
    await results_service.add_result(
        db_session, actor_discord_id=1, ctf_id=ctf_id, placement=2, total_teams=10
    )

    result, changed = await _sync(db_session, ctf_id, placement=9, total_teams=10, score=1.0)

    assert changed is False
    assert result.placement == 2
    assert result.source is ResultSource.MANUAL
