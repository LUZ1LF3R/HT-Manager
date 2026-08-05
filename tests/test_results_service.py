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
    await results_service.upsert_from_ctftime(
        db_session, ctf_id=ctf_id, placement=5, total_teams=50, rating_points=1.2, source_url=None
    )
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
    result, changed = await results_service.upsert_from_ctftime(
        db_session, ctf_id=ctf_id, placement=1, total_teams=10, rating_points=5.0, source_url=None
    )
    assert changed is True
    assert result.source is ResultSource.CTFTIME

    result, changed = await results_service.upsert_from_ctftime(
        db_session, ctf_id=ctf_id, placement=1, total_teams=10, rating_points=5.0, source_url=None
    )
    assert changed is False


async def test_upsert_from_ctftime_reports_change_on_new_placement(
    db_session: AsyncSession,
) -> None:
    ctf_id = await _make_ctf(db_session)
    await results_service.upsert_from_ctftime(
        db_session, ctf_id=ctf_id, placement=3, total_teams=10, rating_points=5.0, source_url=None
    )
    result, changed = await results_service.upsert_from_ctftime(
        db_session, ctf_id=ctf_id, placement=2, total_teams=10, rating_points=5.5, source_url=None
    )
    assert changed is True
    assert result.placement == 2
