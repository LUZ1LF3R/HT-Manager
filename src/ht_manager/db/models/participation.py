from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ht_manager.db.base import Base


class ParticipationSource(enum.StrEnum):
    VOTE = "vote"
    MANUAL = "manual"


class Participation(Base):
    """A member's participation in one CTF (spec §9) — the only XP-like
    concept in the project. At most one row per (ctf_id, discord_user_id)."""

    __tablename__ = "participations"
    __table_args__ = (
        UniqueConstraint(
            "ctf_id", "discord_user_id", name="uq_participations_ctf_id_discord_user_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ctf_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ctfs.id", name="fk_participations_ctf_id_ctfs"), nullable=False
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[ParticipationSource] = mapped_column(
        Enum(
            ParticipationSource,
            name="participation_source",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
