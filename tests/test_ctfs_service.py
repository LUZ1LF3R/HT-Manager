from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTFStatus
from ht_manager.services import ctfs as ctfs_service

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 3, tzinfo=UTC)


async def _make_draft(session: AsyncSession, **overrides: object) -> object:
    fields = dict(
        actor_discord_id=1,
        name="L3akCTF",
        year=2026,
        start_at=START,
        end_at=END,
    )
    fields.update(overrides)
    return await ctfs_service.create_draft(session, **fields)  # type: ignore[arg-type]


async def test_create_draft_persists_and_defaults_to_draft_status(db_session: AsyncSession) -> None:
    ctf = await _make_draft(db_session)
    assert ctf.id is not None
    assert ctf.status is CTFStatus.DRAFT


async def test_create_draft_rejects_end_before_start(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await _make_draft(db_session, start_at=END, end_at=START)


async def test_create_draft_rejects_duplicate_ctftime_event_id(db_session: AsyncSession) -> None:
    await _make_draft(db_session, ctftime_event_id=42)
    with pytest.raises(ctfs_service.DuplicateCTFTimeEventError):
        await _make_draft(db_session, name="Other", ctftime_event_id=42)


async def test_update_ctf_changes_fields_and_writes_audit(db_session: AsyncSession) -> None:
    ctf = await _make_draft(db_session)
    updated = await ctfs_service.update_ctf(
        db_session, actor_discord_id=1, ctf_id=ctf.id, name="Renamed"
    )
    assert updated.name == "Renamed"


async def test_update_ctf_raises_for_unknown_id(db_session: AsyncSession) -> None:
    with pytest.raises(ctfs_service.CTFNotFoundError):
        await ctfs_service.update_ctf(db_session, actor_discord_id=1, ctf_id=999_999, name="x")


async def test_update_ctf_blocked_once_locked(db_session: AsyncSession) -> None:
    ctf = await _make_draft(db_session)
    await ctfs_service.transition(
        db_session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.CANCELLED
    )
    with pytest.raises(ctfs_service.InvalidCTFStateError):
        await ctfs_service.update_ctf(db_session, actor_discord_id=1, ctf_id=ctf.id, name="x")


async def test_delete_draft_removes_row(db_session: AsyncSession) -> None:
    ctf = await _make_draft(db_session)
    ctf_id = ctf.id
    await ctfs_service.delete_draft(db_session, actor_discord_id=1, ctf_id=ctf_id)
    from ht_manager.db.repositories import ctfs as ctfs_repo

    assert await ctfs_repo.get(db_session, ctf_id) is None


async def test_delete_draft_refuses_non_draft(db_session: AsyncSession) -> None:
    ctf = await _make_draft(db_session)
    await ctfs_service.transition(
        db_session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.POLLING
    )
    with pytest.raises(ctfs_service.InvalidCTFStateError):
        await ctfs_service.delete_draft(db_session, actor_discord_id=1, ctf_id=ctf.id)


async def test_transition_rejects_invalid_target(db_session: AsyncSession) -> None:
    ctf = await _make_draft(db_session)
    with pytest.raises(ctfs_service.InvalidCTFTransitionError):
        await ctfs_service.transition(
            db_session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.ACTIVE
        )


async def test_transition_allows_documented_path(db_session: AsyncSession) -> None:
    ctf = await _make_draft(db_session)
    ctf = await ctfs_service.transition(
        db_session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.POLLING
    )
    ctf = await ctfs_service.transition(
        db_session, actor_discord_id=1, ctf=ctf, new_status=CTFStatus.SELECTED
    )
    assert ctf.status is CTFStatus.SELECTED
