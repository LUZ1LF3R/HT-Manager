from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime

import discord
from discord.ext.commands import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_manager.db.models.ctf import CTF
from ht_manager.db.models.sync_state import SyncState
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import sync_state as sync_state_repo
from ht_manager.services import results as results_service
from ht_manager.services.ctftime import CTFTimeClient, CTFTimeError, CTFTimeTeamResult

logger = logging.getLogger(__name__)

SYNC_INTEGRATION_KEY = "ctftime_results"

# Errors are joined into one `sync_state.last_error`; cap it so a bad run
# across many CTFs can't write an unbounded blob.
MAX_ERROR_LENGTH = 1000


async def sync_results(bot: Bot, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """The 12-hour CTFTime result sync (spec §10).

    Candidates are grouped by year because CTFTime exposes results only per
    year (`/api/v1/results/<year>/`), so one HTTP request covers every CTF we
    ran that year instead of one request per CTF.

    Idempotent per CTF: `results_service.upsert_from_ctftime` only reports
    `changed=True` (and only then does this announce) when the stored
    placement/score/team count actually differ, so a re-run over the same
    standings is a no-op.

    A failure on one year or one CTF is recorded and skipped rather than
    aborting the run — but any failure at all keeps `last_success_at` from
    advancing, so a partial run never reports as healthy.
    """
    now = datetime.now(UTC)

    async with session_factory() as session:
        candidates = await ctfs_repo.list_awaiting_result_sync(session, now)

    if not candidates:
        await _record_sync_state(session_factory, now, error=None)
        return

    by_year: dict[int, list[CTF]] = defaultdict(list)
    for ctf in candidates:
        by_year[ctf.year].append(ctf)

    failures: list[str] = []
    client = CTFTimeClient()
    try:
        for year, year_ctfs in sorted(by_year.items()):
            try:
                year_results = await client.get_year_results(year)
            except CTFTimeError as exc:
                logger.exception("CTFTime result sync failed for year=%s", year)
                failures.append(f"year {year}: {exc}")
                continue

            for ctf in year_ctfs:
                try:
                    await _sync_one(
                        bot,
                        session_factory,
                        ctf_id=ctf.id,
                        standings=year_results.get(ctf.ctftime_event_id, []),
                    )
                except Exception as exc:  # noqa: BLE001 - recorded, must not kill the run
                    logger.exception("CTFTime result sync failed for ctf_id=%s", ctf.id)
                    failures.append(f"ctf {ctf.id}: {exc}")
    except Exception as exc:  # noqa: BLE001 - recorded below, must not crash the scheduler
        logger.exception("CTFTime result sync run failed")
        failures.append(str(exc))
    finally:
        await client.aclose()

    error = "; ".join(failures)[:MAX_ERROR_LENGTH] if failures else None
    await _record_sync_state(session_factory, now, error=error)


async def _record_sync_state(
    session_factory: async_sessionmaker[AsyncSession], now: datetime, *, error: str | None
) -> None:
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
    *,
    ctf_id: int,
    standings: list[CTFTimeTeamResult],
) -> None:
    settings = bot.settings  # type: ignore[attr-defined]
    if not standings:
        return

    team_id = int(settings.ctftime_team_id)
    match = next((entry for entry in standings if entry.team_id == team_id), None)
    if match is None:
        return

    async with session_factory() as session, session.begin():
        ctf = await ctfs_repo.get(session, ctf_id)
        if ctf is None:
            # Deleted between listing the candidates and syncing this one.
            return
        result, changed = await results_service.upsert_from_ctftime(
            session,
            actor_discord_id=bot.user.id,
            ctf_id=ctf_id,
            placement=match.place,
            total_teams=len(standings),
            score=match.points,
            source_url=ctf.ctftime_url,
        )
        ctf_name = ctf.name
        placement = result.placement
        total_teams = result.total_teams

    if not changed:
        return

    channel = bot.get_channel(settings.results_channel_id)
    if channel is None:
        logger.warning(
            "Results channel %s not found; skipping announcement for ctf_id=%s",
            settings.results_channel_id,
            ctf_id,
        )
        return
    message = f"**{ctf_name}** — placed {placement}/{total_teams} on CTFTime."
    try:
        await channel.send(message)
    except discord.HTTPException:
        logger.exception("Could not announce result for ctf_id=%s", ctf_id)
