from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ht_manager.db.base import Base


class AuditLog(Base):
    """Immutable record of who did what admin mutation, when (spec §14.2).

    Never updated or deleted, including by the retention/cleanup job.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_table: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
