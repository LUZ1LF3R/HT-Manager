from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ht_manager.db.base import Base


class CTFCategoryStat(Base):
    """Solved/total for one arbitrary category in one CTF (spec §12).
    Category names aren't fixed — whatever the admin reports."""

    __tablename__ = "ctf_category_stats"
    __table_args__ = (
        UniqueConstraint(
            "ctf_id", "category_name", name="uq_ctf_category_stats_ctf_id_category_name"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ctf_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ctfs.id", name="fk_ctf_category_stats_ctf_id_ctfs"), nullable=False
    )
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    solved: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
