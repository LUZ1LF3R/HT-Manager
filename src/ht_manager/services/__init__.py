"""Business logic lives here, owned one module per domain (spec §22.1).

Command handlers under `bot/commands/` are translation-only: they parse the
Discord interaction, call a service function, and format the reply. Services
take plain arguments (never a `discord.Interaction`) so they're unit
testable without a live Discord connection, and they own writes to the
`audit_log` table for any admin mutation they perform (spec §14.2).

Transaction ownership: services and repositories never call `session.commit()`
or `session.rollback()`. The caller — a command handler, a FastAPI route, or
a scheduled job — owns the unit of work (`async with session.begin(): ...`)
and chooses its granularity.

This is *not* one transaction per multi-step sequence. Spec §15.2's
winner-resolution flow is explicit: on failure, leave the CTF in its last
successfully-reached state rather than rolling back to the start, and steps
are individually idempotent so a retry doesn't duplicate work. That means
one transaction per step, not one across the whole chain — and no
transaction may be held open across a Discord API call (steps that call
Discord do so outside any `session.begin()` block), since a stalled Discord
request would otherwise pin a DB connection for its full duration.
"""

from __future__ import annotations
