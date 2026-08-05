from __future__ import annotations

import logging
from datetime import UTC, datetime

import discord
from discord.ext.commands import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_manager.db.models.sync_state import SyncState
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import sync_state as sync_state_repo
from ht_manager.services import results as results_service
from ht_manager.services.ctftime import CTFTimeClient, CTFTimeError

logger = logging.getLogger(__name__)

SYNC_INTEGRATION_KEY = "ctftime_results"


async def sync_results(bot: Bot, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """The 12-hour CTFTime result sync (spec §10). Idempotent per CTF:
    `results_service.upsert_from_ctftime` only reports `changed=True` (and
    only then does this announce) when the stored placement/points/team
    count actually differ, so a re-run over the same standings is a no-op.
    """
    now = datetime.now(UTC)

    async with session_factory() as session:
        candidates = await ctfs_repo.list_awaiting_result_sync(session, now)

    client = CTFTimeClient()
    error: str | None = None
    try:
        for ctf in candidates:
            try:
                await _sync_one(
                    bot,
                    session_factory,
                    client,
                    ctf_id=ctf.id,
                    ctftime_event_id=ctf.ctftime_event_id,
                )
            except CTFTimeError:
                logger.exception("CTFTime result sync failed for ctf_id=%s", ctf.id)
    except Exception as exc:  # noqa: BLE001 - recorded below, must not crash the scheduler
        error = str(exc)
        logger.exception("CTFTime result sync run failed")
    finally:
        await client.aclose()

    async with session_factory() as session, session.begin():
        state = await sync_state_repo.get(session, SYNC_INTEGRATION_KEY)
        if state is None:
            state = await sync_state_repo.add(
                session, SyncState(integration_key=SYNC_INTEGRATION_KEY)
            )
        if error is None:
            state.last_success_at = now
            state.last_error = None
        else:
            state.last_error = error


async def _sync_one(
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    client: CTFTimeClient,
    *,
    ctf_id: int,
    ctftime_event_id: int,
) -> None:
    settings = bot.settings  # type: ignore[attr-defined]
    standings = await client.get_event_results(ctftime_event_id)
    if not standings:
        return

    team_id = int(settings.ctftime_team_id)
    match = next((entry for entry in standings if entry.team_id == team_id), None)
    if match is None:
        return

    async with session_factory() as session, session.begin():
        ctf = await ctfs_repo.get(session, ctf_id)
        result, changed = await results_service.upsert_from_ctftime(
            session,
            ctf_id=ctf_id,
            placement=match.place,
            total_teams=len(standings),
            rating_points=match.points,
            source_url=ctf.ctftime_url,
        )
        ctf_name = ctf.name

    if not changed:
        return

    channel = bot.get_channel(settings.results_channel_id)
    if channel is None:
        return
    message = f"**{ctf_name}** — placed {result.placement}/{result.total_teams} on CTFTime."
    try:
        await channel.send(message)
    except discord.HTTPException:
        logger.exception("Could not announce result for ctf_id=%s", ctf_id)
