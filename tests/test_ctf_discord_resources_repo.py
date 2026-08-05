from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf_discord_resource import CTFDiscordResource
from ht_manager.db.repositories import ctf_discord_resources as resources_repo
from ht_manager.services import ctfs as ctfs_service

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 3, tzinfo=UTC)


async def _make_ctf(session: AsyncSession) -> int:
    ctf = await ctfs_service.create_draft(
        session, actor_discord_id=1, name="A", year=2026, start_at=START, end_at=END
    )
    return ctf.id


async def test_list_due_for_cleanup_excludes_future_and_cleaned(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    past_ctf = await _make_ctf(db_session)
    future_ctf = await _make_ctf(db_session)
    cleaned_ctf = await _make_ctf(db_session)

    await resources_repo.add(
        db_session,
        CTFDiscordResource(ctf_id=past_ctf, role_id=1, cleanup_after=now - timedelta(days=1)),
    )
    await resources_repo.add(
        db_session,
        CTFDiscordResource(ctf_id=future_ctf, role_id=2, cleanup_after=now + timedelta(days=1)),
    )
    await resources_repo.add(
        db_session,
        CTFDiscordResource(
            ctf_id=cleaned_ctf,
            role_id=3,
            cleanup_after=now - timedelta(days=1),
            cleaned_at=now,
        ),
    )

    due = await resources_repo.list_due_for_cleanup(db_session, now)
    assert {r.ctf_id for r in due} == {past_ctf}


async def test_mark_cleaned_sets_timestamp(db_session: AsyncSession) -> None:
    ctf_id = await _make_ctf(db_session)
    resource = await resources_repo.add(
        db_session, CTFDiscordResource(ctf_id=ctf_id, role_id=1, cleanup_after=datetime.now(UTC))
    )
    now = datetime.now(UTC)
    await resources_repo.mark_cleaned(db_session, resource, now)
    refreshed = await resources_repo.get_by_ctf_id(db_session, ctf_id)
    assert refreshed.cleaned_at is not None
