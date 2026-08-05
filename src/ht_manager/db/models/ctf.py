from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ht_manager.db.base import Base


class CTFStatus(enum.StrEnum):
    DRAFT = "draft"
    POLLING = "polling"
    TIED = "tied"
    SELECTED = "selected"
    ACTIVE = "active"
    FINISHED = "finished"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class CTF(Base):
    """A CTF event tracked through the pipeline (spec §14, §15)."""

    __tablename__ = "ctfs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    ctftime_event_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    ctftime_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    official_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[CTFStatus] = mapped_column(
        Enum(
            CTFStatus,
            name="ctf_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=CTFStatus.DRAFT,
        server_default=CTFStatus.DRAFT.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
