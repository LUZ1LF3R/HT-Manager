"""Data-access layer, one module per aggregate.

Repositories take an `AsyncSession` and return/persist ORM models. They own
no business rules — those live in `services/`. Nothing outside
`db/repositories/` should build a SQLAlchemy query directly against a model.

Transaction ownership: repositories never call `session.commit()` or
`session.rollback()` — see `services/__init__.py` for the full rule,
including why multi-step sequences use one transaction per step rather than
one across the whole sequence. A repository method flushes if it needs
generated PKs before returning, but the caller decides when the unit of
work ends.
"""

from __future__ import annotations
