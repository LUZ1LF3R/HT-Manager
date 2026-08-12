from __future__ import annotations

from ht_manager.bot.formatting import (
    DISCORD_MESSAGE_LIMIT,
    code_block,
    truncate_for_discord,
)


def test_short_text_is_untouched() -> None:
    assert truncate_for_discord("hello") == "hello"


def test_over_long_text_is_clamped_to_the_limit() -> None:
    clamped = truncate_for_discord("x" * 5000)
    assert len(clamped) == DISCORD_MESSAGE_LIMIT
    assert clamped.endswith("(truncated)")


def test_code_block_result_still_fits_including_its_fences() -> None:
    """The ``` fences count against Discord's 2000-character budget, so a
    long summary must be truncated to leave room for them."""
    wrapped = code_block("y" * 5000)
    assert len(wrapped) <= DISCORD_MESSAGE_LIMIT
    assert wrapped.startswith("```\n")
    assert wrapped.endswith("\n```")
