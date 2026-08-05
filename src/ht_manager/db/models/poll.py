from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ht_manager.db.base import Base


class PollStatus(enum.StrEnum):
    DRAFTING = "drafting"
    OPEN = "open"
    CLOSED = "closed"
    TIED = "tied"
    CANCELLED = "cancelled"


class Poll(Base):
    """A `/nextctf` curation/voting session (spec §7, §14)."""

    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[PollStatus] = mapped_column(
        Enum(
            PollStatus,
            name="poll_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PollStatus.DRAFTING,
        server_default=PollStatus.DRAFTING.value,
    )
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    winning_ctf_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ctfs.id", name="fk_polls_winning_ctf_id_ctfs"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PollOption(Base):
    """A candidate CTF in a poll's draft/vote (spec §14)."""

    __tablename__ = "poll_options"
    __table_args__ = (UniqueConstraint("poll_id", "ctf_id", name="uq_poll_options_poll_id_ctf_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    poll_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("polls.id", name="fk_poll_options_poll_id_polls"), nullable=False
    )
    ctf_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ctfs.id", name="fk_poll_options_ctf_id_ctfs"), nullable=False
    )
    option_index: Mapped[int] = mapped_column(Integer, nullable=False)


class PollVote(Base):
    """One member's vote for one option (spec §14). Single-choice polls only,
    so a member has at most one vote per poll."""

    __tablename__ = "poll_votes"
    __table_args__ = (
        UniqueConstraint(
            "poll_id", "discord_user_id", name="uq_poll_votes_poll_id_discord_user_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    poll_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("polls.id", name="fk_poll_votes_poll_id_polls"), nullable=False
    )
    ctf_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ctfs.id", name="fk_poll_votes_ctf_id_ctfs"), nullable=False
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
