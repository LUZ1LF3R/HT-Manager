from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_manager.db.models.ctf import CTFStatus
from ht_manager.db.models.ctf_discord_resource import CTFDiscordResource
from ht_manager.db.repositories import ctf_discord_resources as resources_repo
from ht_manager.jobs import cleanup
from ht_manager.services import ctfs as ctfs_service


def _fake_bot() -> SimpleNamespace:
    return SimpleNamespace(
        settings=SimpleNamespace(discord_guild_id=1, ctf_archive_category_id=999)
    )


async def _make_finished_ctf(session: AsyncSession) -> int:
    start_at = datetime.now(UTC) - timedelta(days=10)
    end_at = datetime.now(UTC) - timedelta(days=5)
    ctf = await ctfs_service.create_draft(
        session, actor_discord_id=1, name="L3akCTF", year=2026, start_at=start_at, end_at=end_at
    )
    for status in (CTFStatus.POLLING, CTFStatus.SELECTED, CTFStatus.ACTIVE, CTFStatus.FINISHED):
        await ctfs_service.transition(session, actor_discord_id=1, ctf=ctf, new_status=status)
    return ctf.id


async def test_archive_finished_workspaces_moves_due_forum_and_marks_archived(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with db_session_factory() as session, session.begin():
        ctf_id = await _make_finished_ctf(session)
        await resources_repo.add(
            session,
            CTFDiscordResource(
                ctf_id=ctf_id,
                role_id=1,
                forum_channel_id=2,
                thread_id=3,
                archive_after=datetime.now(UTC) - timedelta(minutes=1),
            ),
        )

    moves: list[tuple[int, int]] = []

    async def fake_move(bot, *, guild_id, forum_channel_id, category_id):
        moves.append((forum_channel_id, category_id))

    monkeypatch.setattr(cleanup.discord_resources, "move_forum_to_category", fake_move)

    await cleanup.archive_finished_workspaces(_fake_bot(), db_session_factory)

    assert moves == [(2, 999)]
    async with db_session_factory() as session:
        resource = await resources_repo.get_by_ctf_id(session, ctf_id)
        assert resource.archived_at is not None


async def test_archive_finished_workspaces_skips_not_yet_due(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with db_session_factory() as session, session.begin():
        ctf_id = await _make_finished_ctf(session)
        await resources_repo.add(
            session,
            CTFDiscordResource(
                ctf_id=ctf_id,
                role_id=1,
                forum_channel_id=2,
                thread_id=3,
                archive_after=datetime.now(UTC) + timedelta(days=1),
            ),
        )

    moves: list[tuple[int, int]] = []

    async def fake_move(bot, *, guild_id, forum_channel_id, category_id):
        moves.append((forum_channel_id, category_id))

    monkeypatch.setattr(cleanup.discord_resources, "move_forum_to_category", fake_move)

    await cleanup.archive_finished_workspaces(_fake_bot(), db_session_factory)

    assert moves == []
    async with db_session_factory() as session:
        resource = await resources_repo.get_by_ctf_id(session, ctf_id)
        assert resource.archived_at is None


async def test_archive_finished_workspaces_is_idempotent(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with db_session_factory() as session, session.begin():
        ctf_id = await _make_finished_ctf(session)
        await resources_repo.add(
            session,
            CTFDiscordResource(
                ctf_id=ctf_id,
                role_id=1,
                forum_channel_id=2,
                thread_id=3,
                archive_after=datetime.now(UTC) - timedelta(minutes=1),
            ),
        )

    move_count = 0

    async def fake_move(bot, *, guild_id, forum_channel_id, category_id):
        nonlocal move_count
        move_count += 1

    monkeypatch.setattr(cleanup.discord_resources, "move_forum_to_category", fake_move)

    await cleanup.archive_finished_workspaces(_fake_bot(), db_session_factory)
    await cleanup.archive_finished_workspaces(_fake_bot(), db_session_factory)

    assert move_count == 1
