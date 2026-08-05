from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.result import Result, ResultSource
from ht_manager.db.repositories import audit_log as audit_log_repo
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import results as results_repo

_EDITABLE_FIELDS = (
    "placement",
    "total_teams",
    "score",
    "rating_points",
    "source_url",
    "notes",
)


class CTFNotFoundError(Exception):
    pass


class DuplicateResultError(Exception):
    pass


class ResultNotFoundError(Exception):
    pass


async def add_result(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    ctf_id: int,
    placement: int | None = None,
    total_teams: int | None = None,
    score: float | None = None,
    rating_points: float | None = None,
    source_url: str | None = None,
    notes: str | None = None,
) -> Result:
    if await ctfs_repo.get(session, ctf_id) is None:
        raise CTFNotFoundError(f"CTF {ctf_id} not found")
    if await results_repo.get_by_ctf_id(session, ctf_id) is not None:
        raise DuplicateResultError(f"CTF {ctf_id} already has a result — use /editresult")

    result = await results_repo.add(
        session,
        Result(
            ctf_id=ctf_id,
            source=ResultSource.MANUAL,
            placement=placement,
            total_teams=total_teams,
            score=score,
            rating_points=rating_points,
            source_url=source_url,
            notes=notes,
        ),
    )
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="result_added",
        target_table="results",
        target_id=result.id,
        before=None,
        after=_snapshot(result),
    )
    return result


async def edit_result(
    session: AsyncSession, *, actor_discord_id: int, ctf_id: int, **changes: Any
) -> Result:
    result = await results_repo.get_by_ctf_id(session, ctf_id)
    if result is None:
        raise ResultNotFoundError(f"CTF {ctf_id} has no result yet — use /addresult")

    unknown = set(changes) - set(_EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported field(s): {', '.join(sorted(unknown))}")

    before = _snapshot(result)
    for field, value in changes.items():
        setattr(result, field, value)
    result.source = ResultSource.MANUAL
    await session.flush()

    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="result_edited",
        target_table="results",
        target_id=result.id,
        before=before,
        after=_snapshot(result),
    )
    return result


async def upsert_from_ctftime(
    session: AsyncSession,
    *,
    ctf_id: int,
    placement: int,
    total_teams: int | None,
    rating_points: float | None,
    source_url: str | None,
) -> tuple[Result, bool]:
    """Syncs one CTF's result from CTFTime (spec §10). Returns
    `(result, changed)` — `changed=False` means the stored data already
    matched, so the caller must not re-announce it (spec: "do not spam
    identical results on every scheduled run")."""
    existing = await results_repo.get_by_ctf_id(session, ctf_id)
    if existing is not None:
        unchanged = (
            existing.placement == placement
            and existing.total_teams == total_teams
            and existing.rating_points == rating_points
        )
        if unchanged:
            return existing, False
        existing.placement = placement
        existing.total_teams = total_teams
        existing.rating_points = rating_points
        existing.source_url = source_url
        existing.source = ResultSource.CTFTIME
        existing.announced_at = datetime.now(UTC)
        await session.flush()
        return existing, True

    result = await results_repo.add(
        session,
        Result(
            ctf_id=ctf_id,
            source=ResultSource.CTFTIME,
            placement=placement,
            total_teams=total_teams,
            rating_points=rating_points,
            source_url=source_url,
            announced_at=datetime.now(UTC),
        ),
    )
    return result, True


def _snapshot(result: Result) -> dict[str, Any]:
    return {field: getattr(result, field) for field in _EDITABLE_FIELDS}
