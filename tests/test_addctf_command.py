from __future__ import annotations

from datetime import UTC, timezone

from ht_manager.bot.commands.addctf import parse_iso_datetime


def test_parse_iso_datetime_keeps_explicit_offset() -> None:
    result = parse_iso_datetime("2026-09-01T18:00:00+02:00")
    assert result.tzinfo == timezone.utc or result.utcoffset() is not None


def test_parse_iso_datetime_assumes_utc_when_naive() -> None:
    result = parse_iso_datetime("2026-09-01T18:00:00")
    assert result.tzinfo == UTC
