from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_manager.db.models.ctf import CTFStatus
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import sync_state as sync_state_repo
from ht_manager.jobs import result_sync
from ht_manager.jobs.result_sync import SYNC_INTEGRATION_KEY
from ht_manager.services import ctfs as ctfs_service
from ht_manager.services import results as results_service
from ht_manager.services.ctftime import CTFTimeError, CTFTimeTeamResult

TEAM_ID = 999


class _FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)


def _fake_bot(channel: _FakeChannel | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        settings=SimpleNamespace(ctftime_team_id=str(TEAM_ID), results_channel_id=1),
        user=SimpleNamespace(id=42),
        get_channel=lambda _channel_id: channel,
    )


def _fake_client_factory(monkeypatch: pytest.MonkeyPatch, *, years: dict, calls: list[int]):
    class _FakeClient:
        async def get_year_results(self, year: int):
            calls.append(year)
            value = years.get(year, {})
            if isinstance(value, Exception):
                raise value
            return value

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(result_sync, "CTFTimeClient", _FakeClient)


async def _make_finished_ctf(
    session: AsyncSession, *, name: str, event_id: int, year: int, ended_days_ago: int = 1
) -> int:
    end_at = datetime.now(UTC) - timedelta(days=ended_days_ago)
    ctf = await ctfs_service.create_draft(
        session,
        actor_discord_id=1,
        name=name,
        year=year,
        start_at=end_at - timedelta(days=2),
        end_at=end_at,
        ctftime_event_id=event_id,
    )
    for status in (CTFStatus.POLLING, CTFStatus.SELECTED, CTFStatus.ACTIVE, CTFStatus.FINISHED):
        await ctfs_service.transition(
            session, actor_discord_id=1, ctf=ctf, new_status=status
        )
    return ctf.id


async def test_sync_announces_and_records_success(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with db_session_factory() as session, session.begin():
        ctf_id = await _make_finished_ctf(session, name="L3akCTF", event_id=42, year=2026)

    calls: list[int] = []
    _fake_client_factory(
        monkeypatch,
        years={
            2026: {42: [
                CTFTimeTeamResult(place=1, points=9000.0, team_id=5),
                CTFTimeTeamResult(place=47, points=8214.0, team_id=TEAM_ID),
            ]}
        },
        calls=calls,
    )
    channel = _FakeChannel()

    await result_sync.sync_results(_fake_bot(channel), db_session_factory)

    assert calls == [2026]
    assert len(channel.sent) == 1
    assert "placed 47/2" in channel.sent[0]

    async with db_session_factory() as session:
        state = await sync_state_repo.get(session, SYNC_INTEGRATION_KEY)
        assert state.last_success_at is not None
        assert state.last_error is None
        from ht_manager.db.repositories import results as results_repo

        result = await results_repo.get_by_ctf_id(session, ctf_id)
        assert result.placement == 47
        assert result.score == 8214.0


async def test_sync_fetches_one_request_per_year_not_per_ctf(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with db_session_factory() as session, session.begin():
        await _make_finished_ctf(session, name="A", event_id=1, year=2026)
        await _make_finished_ctf(session, name="B", event_id=2, year=2026)
        await _make_finished_ctf(session, name="C", event_id=3, year=2026)

    calls: list[int] = []
    _fake_client_factory(monkeypatch, years={2026: {}}, calls=calls)

    await result_sync.sync_results(_fake_bot(), db_session_factory)

    assert calls == [2026]


async def test_partial_failure_does_not_report_success(
    db_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run where CTFTime was unreachable for one year must not stamp
    `last_success_at` — that field is the only signal the sync is healthy."""
    async with db_session_factory() as session, session.begin():
        await _make_finished_ctf(session, name="Old", event_id=1, year=2025, ended_days_ago=40)
        await _make_finished_ctf(session, name="New", event_id=2, year=2026)

    calls: list[int] = []
    _fake_client_factory(
        monkeypatch,
        years={2025: CTFTimeError("ctftime is down"), 2026: {}},
        calls=calls,
    )

    await result_sync.sync_results(_fake_bot(), db_session_factory)

    assert calls == [2025, 2026], "one year failing must not abort the other"
    async with db_session_factory() as session:
        state = await sync_state_repo.get(session, SYNC_INTEGRATION_KEY)
        assert state.last_success_at is None
        assert "ctftime is down" in state.last_error


async def test_sync_skips_ctfs_outside_the_window_or_corrected_by_hand(
    db_session: AsyncSession,
) -> None:
    recent = await _make_finished_ctf(db_session, name="Recent", event_id=1, year=2026)
    await _make_finished_ctf(
        db_session, name="Ancient", event_id=2, year=2020, ended_days_ago=400
    )
    manual = await _make_finished_ctf(db_session, name="Manual", event_id=3, year=2026)
    await results_service.add_result(
        db_session, actor_discord_id=1, ctf_id=manual, placement=2
    )

    candidates = await ctfs_repo.list_awaiting_result_sync(db_session, datetime.now(UTC))

    assert [ctf.id for ctf in candidates] == [recent]
