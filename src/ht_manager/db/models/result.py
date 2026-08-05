from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ht_manager.db.base import Base


class ResultSource(enum.StrEnum):
    CTFTIME = "ctftime"
    MANUAL = "manual"


class Result(Base):
    """One CTF's placement/score (spec §10, §11, §14). At most one row per
    CTF — `/editresult` corrects it in place rather than creating a second
    row, which is what makes duplicate-announcement prevention trivial."""

    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("ctf_id", name="uq_results_ctf_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ctf_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ctfs.id", name="fk_results_ctf_id_ctfs"), nullable=False
    )
    source: Mapped[ResultSource] = mapped_column(
        Enum(
            ResultSource,
            name="result_source",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    placement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_teams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
