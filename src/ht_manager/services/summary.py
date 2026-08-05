from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.ctf import CTFStatus
from ht_manager.db.models.ctf_category_stat import CTFCategoryStat
from ht_manager.db.repositories import audit_log as audit_log_repo
from ht_manager.db.repositories import category_stats as category_stats_repo
from ht_manager.db.repositories import ctfs as ctfs_repo
from ht_manager.db.repositories import participation as participation_repo
from ht_manager.db.repositories import results as results_repo
from ht_manager.services import ctfs as ctfs_service


class CTFNotFoundError(Exception):
    pass


async def set_category_stat(
    session: AsyncSession,
    *,
    actor_discord_id: int,
    ctf_id: int,
    category_name: str,
    solved: int,
    total: int,
) -> CTFCategoryStat:
    if await ctfs_repo.get(session, ctf_id) is None:
        raise CTFNotFoundError(f"CTF {ctf_id} not found")

    existing = await category_stats_repo.get(session, ctf_id=ctf_id, category_name=category_name)
    before = None
    if existing is not None:
        before = {"solved": existing.solved, "total": existing.total}
        existing.solved = solved
        existing.total = total
        await session.flush()
        stat = existing
    else:
        stat = await category_stats_repo.add(
            session,
            CTFCategoryStat(
                ctf_id=ctf_id, category_name=category_name, solved=solved, total=total
            ),
        )

    await audit_log_repo.record(
        session,
        discord_user_id=actor_discord_id,
        action="category_stat_set",
        target_table="ctf_category_stats",
        target_id=stat.id,
        before=before,
        after={"category_name": category_name, "solved": solved, "total": total},
    )
    return stat


async def finish_ctf(session: AsyncSession, *, actor_discord_id: int, ctf_id: int) -> str:
    """`/endctf` (spec §12): transitions the CTF to `FINISHED` and returns
    the rendered summary — built only from data actually on hand, per the
    spec's "do not invent category totals" rule."""
    ctf = await ctfs_repo.get(session, ctf_id)
    if ctf is None:
        raise CTFNotFoundError(f"CTF {ctf_id} not found")

    await ctfs_service.transition(
        session, actor_discord_id=actor_discord_id, ctf=ctf, new_status=CTFStatus.FINISHED
    )
    return await render_summary(session, ctf_id)


async def render_summary(session: AsyncSession, ctf_id: int) -> str:
    ctf = await ctfs_repo.get(session, ctf_id)
    if ctf is None:
        raise CTFNotFoundError(f"CTF {ctf_id} not found")

    lines = [f"{ctf.name} — {ctf.status.value.capitalize()}"]

    result = await results_repo.get_by_ctf_id(session, ctf_id)
    if result is not None:
        if result.placement is not None:
            total = f" / {result.total_teams}" if result.total_teams else ""
            lines.append(f"Placement: {result.placement}{total}")
        if result.score is not None:
            lines.append(f"Score: {result.score:g}")

    stats = await category_stats_repo.list_for_ctf(session, ctf_id)
    if stats:
        lines.append("Solves")
        name_width = max(len(stat.category_name) for stat in stats)
        for stat in stats:
            lines.append(f"  {stat.category_name.ljust(name_width)} {stat.solved}/{stat.total}")
        total_solved = sum(stat.solved for stat in stats)
        total_challenges = sum(stat.total for stat in stats)
        lines.append(f"Total solved: {total_solved}/{total_challenges}")

    participants = await participation_repo.list_for_ctf(session, ctf_id)
    lines.append(f"Participants: {len(participants)}")

    return "\n".join(lines)
