from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ht_manager.db.base import Base


class SyncState(Base):
    """Tracks one external integration's last run (spec §14) — currently
    just the CTFTime result sync's `integration_key="ctftime_results"`."""

    __tablename__ = "sync_state"
    __table_args__ = (UniqueConstraint("integration_key", name="uq_sync_state_integration_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    integration_key: Mapped[str] = mapped_column(String(100), nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
