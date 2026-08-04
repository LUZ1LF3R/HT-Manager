from __future__ import annotations

from ht_manager.bot.client import build_bot
from ht_manager.config import get_settings


def main() -> None:
    settings = get_settings()
    bot = build_bot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
