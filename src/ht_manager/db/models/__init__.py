"""Model registration point.

Every SQLAlchemy model module under `ht_manager.db.models` MUST be imported
here so its table is registered on `Base.metadata` before Alembic
autogenerate (or `alembic check`) runs. A model module that exists but isn't
imported here is invisible to migrations — autogenerate can even emit a
`DROP TABLE` for it, since as far as the metadata is concerned the table
doesn't exist. `tests/test_db_models_registration.py` enforces this.

Example, once M1 adds a model:
    from ht_manager.db.models.ctf import CTF  # noqa: F401
"""

from __future__ import annotations

__all__: list[str] = []
