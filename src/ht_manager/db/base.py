from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Named so Alembic autogenerate emits real constraint names instead of
# `None` (which fails on `op.drop_constraint(None, ...)` at runtime). Must
# be set before the first migration is generated — renaming constraints on
# already-applied tables means a follow-up migration, since migrations are
# never edited once applied (spec §5.1).
#
# The "ck" convention requires every CheckConstraint to have an explicit
# name — including ones SQLAlchemy generates implicitly from a `Boolean` or
# non-native `Enum` column. Pass `name=` explicitly (or `create_constraint=
# False` on the Enum) or class definition will raise at import time.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
