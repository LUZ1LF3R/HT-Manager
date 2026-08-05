from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ht_manager.db.base import Base


class CTFDiscordResource(Base):
    """Discord-side role/workspace IDs for one CTF (spec §8, §14.3) — these
    rows survive Discord-side cleanup; only `cleaned_at` reflects that the
    role/thread have been deleted, the row itself is never removed."""

    __tablename__ = "ctf_discord_resources"
    __table_args__ = (UniqueConstraint("ctf_id", name="uq_ctf_discord_resources_ctf_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ctf_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ctfs.id", name="fk_ctf_discord_resources_ctf_id_ctfs"), nullable=False
    )
    role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forum_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cleanup_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
