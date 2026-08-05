from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTF, CTFStatus
from ht_manager.db.repositories import audit_log as audit_log_repo
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.services.ctftime import CTFTimeEvent

# Spec §15.1: transitions not listed here are invalid and must be rejected.
ALLOWED_TRANSITIONS: dict[CTFStatus, set[CTFStatus]] = {
    CTFStatus.DRAFT: {CTFStatus.POLLING, CTFStatus.CANCELLED},
    CTFStatus.POLLING: {CTFStatus.SELECTED, CTFStatus.TIED, CTFStatus.CANCELLED},
    CTFStatus.TIED: {CTFStatus.SELECTED, CTFStatus.CANCELLED},
    CTFStatus.SELECTED: {CTFStatus.ACTIVE, CTFStatus.CANCELLED},
    CTFStatus.ACTIVE: {CTFStatus.FINISHED, CTFStatus.CANCELLED},
    CTFStatus.FINISHED: {CTFStatus.ARCHIVED},
    CTFStatus.ARCHIVED: set(),
    CTFStatus.CANCELLED: set(),
}

# Statuses whose metadata may no longer be corrected via /editctf.
LOCKED_STATUSES = {CTFStatus.ARCHIVED, CTFStatus.CANCELLED}

_EDITABLE_FIELDS = (
    "name",
    "year",
    "ctftime_event_id",
    "ctftime_url",
    "official_url",
    "start_at",
    "end_at",
    "weight",
)


class CTFNotFoundError(Exception):
    pass


class InvalidCTFStateError(Exception):
    pass


class DuplicateCTFTimeEventError(Exception):
    pass


class InvalidCTFTransitionError(Exception):
    pass


def _snapshot(ctf: CTF) -> dict[str, Any]:
    return {field: _jsonable(getattr(ctf, field)) for field in _EDITABLE_FIELDS}


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def create_draft(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    name: str,
    year: int,
    start_at: datetime,
    end_at: datetime,
    ctftime_event_id: int | None = None,
    ctftime_url: str | None = None,
    official_url: str | None = None,
    weight: float | None = None,
) -> CTF:
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")

    if ctftime_event_id is not None:
        existing = await ctfs_repo.get_by_ctftime_event_id(session, ctftime_event_id)
        if existing is not None:
            raise DuplicateCTFTimeEventError(
                f"CTF {existing.id} already uses ctftime_event_id={ctftime_event_id}"
            )

    ctf = CTF(
        name=name,
        year=year,
        start_at=start_at,
        end_at=end_at,
        ctftime_event_id=ctftime_event_id,
        ctftime_url=ctftime_url,
        official_url=official_url,
        weight=weight,
        status=CTFStatus.DRAFT,
    )
    await ctfs_repo.add(session, ctf)
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="ctf_created",
        target_table="ctfs",
        target_id=ctf.id,
        before=None,
        after=_snapshot(ctf),
    )
    return ctf


async def get_or_create_from_ctftime(
    session: AsyncSession, *, actor_discord_id: int, event: CTFTimeEvent
) -> CTF:
    """Dedups on `ctftime_event_id` (spec §7.3) — re-fetching the same
    upcoming event across `/nextctf` runs must not create duplicate drafts."""
    existing = await ctfs_repo.get_by_ctftime_event_id(session, event.ctftime_event_id)
    if existing is not None:
        return existing
    return await create_draft(
        session,
        actor_discord_id=actor_discord_id,
        name=event.name,
        year=event.start_at.year,
        start_at=event.start_at,
        end_at=event.end_at,
        ctftime_event_id=event.ctftime_event_id,
        ctftime_url=event.ctftime_url,
        official_url=event.official_url,
        weight=event.weight,
    )


async def update_ctf(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    ctf_id: int,
    **changes: Any,
) -> CTF:
    ctf = await ctfs_repo.get(session, ctf_id)
    if ctf is None:
        raise CTFNotFoundError(f"CTF {ctf_id} not found")
    if ctf.status in LOCKED_STATUSES:
        raise InvalidCTFStateError(
            f"CTF {ctf_id} is {ctf.status.value} and can no longer be edited"
        )

    unknown = set(changes) - set(_EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported field(s): {', '.join(sorted(unknown))}")

    before = _snapshot(ctf)

    new_start = changes.get("start_at", ctf.start_at)
    new_end = changes.get("end_at", ctf.end_at)
    if new_end <= new_start:
        raise ValueError("end_at must be after start_at")

    new_ctftime_event_id = changes.get("ctftime_event_id", ctf.ctftime_event_id)
    if new_ctftime_event_id is not None and new_ctftime_event_id != ctf.ctftime_event_id:
        existing = await ctfs_repo.get_by_ctftime_event_id(session, new_ctftime_event_id)
        if existing is not None and existing.id != ctf.id:
            raise DuplicateCTFTimeEventError(
                f"CTF {existing.id} already uses ctftime_event_id={new_ctftime_event_id}"
            )

    for field, value in changes.items():
        setattr(ctf, field, value)
    await session.flush()

    after = _snapshot(ctf)
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="ctf_updated",
        target_table="ctfs",
        target_id=ctf.id,
        before=before,
        after=after,
    )
    return ctf


async def delete_draft(session: AsyncSession, *, actor_discord_id: int, ctf_id: int) -> None:
    """Hard-delete per spec §14.3: only DRAFT CTFs have no history to protect."""
    ctf = await ctfs_repo.get(session, ctf_id)
    if ctf is None:
        raise CTFNotFoundError(f"CTF {ctf_id} not found")
    if ctf.status is not CTFStatus.DRAFT:
        raise InvalidCTFStateError(
            f"CTF {ctf_id} is {ctf.status.value}, not draft; use /archivectf or the CANCELLED path"
        )

    before = _snapshot(ctf)
    await ctfs_repo.delete(session, ctf)
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="ctf_deleted",
        target_table="ctfs",
        target_id=ctf_id,
        before=before,
        after=None,
    )


async def transition(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    ctf: CTF,
    new_status: CTFStatus,
) -> CTF:
    allowed = ALLOWED_TRANSITIONS.get(ctf.status, set())
    if new_status not in allowed:
        raise InvalidCTFTransitionError(
            f"Cannot transition CTF from {ctf.status.value} to {new_status.value}"
        )

    before = {"status": ctf.status.value}
    ctf.status = new_status
    await session.flush()
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="ctf_status_changed",
        target_table="ctfs",
        target_id=ctf.id,
        before=before,
        after={"status": ctf.status.value},
    )
    return ctf
