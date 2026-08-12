from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.participation import Participation, ParticipationSource
from ht_manager.db.repositories import audit_log as audit_log_repo
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import participation as participation_repo


class CTFNotFoundError(Exception):
    pass


class DuplicateParticipationError(Exception):
    pass


class ParticipationNotFoundError(Exception):
    pass


async def add_participation(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    ctf_id: int,
    discord_user_id: int,
    source: ParticipationSource = ParticipationSource.MANUAL,
) -> Participation:
    if await ctfs_repo.get(session, ctf_id) is None:
        raise CTFNotFoundError(f"CTF {ctf_id} not found")

    existing = await participation_repo.get(session, ctf_id=ctf_id, discord_user_id=discord_user_id)
    if existing is not None:
        raise DuplicateParticipationError(
            f"discord_user_id={discord_user_id} already participated in CTF {ctf_id}"
        )
    participation = await participation_repo.add(
        session, Participation(ctf_id=ctf_id, discord_user_id=discord_user_id, source=source)
    )
    if source is ParticipationSource.MANUAL:
        await audit_log_repo.record(
            session,
            discord_user_id=actor_discord_id,
            action="participation_added",
            target_table="participations",
            target_id=participation.id,
            before=None,
            after={"ctf_id": ctf_id, "discord_user_id": discord_user_id, "source": source.value},
        )
    return participation


async def record_from_vote(session: AsyncSession, *, ctf_id: int, discord_user_id: int) -> None:
    """Called from the winner-resolution sequence (spec §15.2 step 3) for
    every voter of the winning option — not an admin action, so no audit
    row. Silently idempotent: a retry after a partial failure must not
    error on rows it already created."""
    existing = await participation_repo.get(session, ctf_id=ctf_id, discord_user_id=discord_user_id)
    if existing is not None:
        return
    await participation_repo.add(
        session,
        Participation(
            ctf_id=ctf_id, discord_user_id=discord_user_id, source=ParticipationSource.VOTE
        ),
    )


async def remove_participation(
    session: AsyncSession, *, actor_discord_id: int, ctf_id: int, discord_user_id: int
) -> None:
    existing = await participation_repo.get(session, ctf_id=ctf_id, discord_user_id=discord_user_id)
    if existing is None:
        raise ParticipationNotFoundError(
            f"discord_user_id={discord_user_id} has no participation record for CTF {ctf_id}"
        )
    before = {"ctf_id": ctf_id, "discord_user_id": discord_user_id, "source": existing.source.value}
    await participation_repo.delete(session, existing)
    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="participation_removed",
        target_table="participations",
        target_id=None,
        before=before,
        after=None,
    )
