from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.db.models.audit_log import AuditLog


async def record(
    session: AsyncSession,
    *,
    discord_user_id: int,
    action: str,
    target_table: str,
    target_id: int | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> AuditLog:
    entry = AuditLog(
        discord_user_id=discord_user_id,
        action=action,
        target_table=target_table,
        target_id=target_id,
        before=before,
        after=after,
    )
    session.add(entry)
    await session.flush()
    return entry
