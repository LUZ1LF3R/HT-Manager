from __future__ import annotations

# Discord rejects message content longer than 2000 characters outright.
DISCORD_MESSAGE_LIMIT = 2000
TRUNCATION_MARKER = "\n… (truncated)"

# ```\n … \n``` — the wrapper a code-blocked message spends from its budget.
CODE_BLOCK_OVERHEAD = 8


def truncate_for_discord(text: str, *, limit: int = DISCORD_MESSAGE_LIMIT) -> str:
    """Clamps `text` to Discord's message-content limit.

    A summary with many categories, or a participant list for a large CTF,
    can cross 2000 characters. Discord rejects an over-long send with a 400,
    so without this the user gets no message at all rather than a long one.
    """
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER


def code_block(text: str) -> str:
    """Wraps `text` in a fenced code block, truncating so the result still
    fits inside Discord's message limit."""
    body = truncate_for_discord(text, limit=DISCORD_MESSAGE_LIMIT - CODE_BLOCK_OVERHEAD)
    return f"```\n{body}\n```"
