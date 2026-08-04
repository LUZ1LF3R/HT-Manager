from __future__ import annotations

import asyncio
import logging

from ht_manager.bot.client import build_bot
from ht_manager.config import Settings, SettingsError, get_settings
from ht_manager.db.session import create_engine, create_session_factory
from ht_manager.logging import configure_logging

logger = logging.getLogger(__name__)


async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    bot = build_bot(settings, session_factory)
    try:
        async with bot:
            await bot.start(settings.discord_token)
    finally:
        await engine.dispose()


def main() -> None:
    try:
        settings = get_settings()
    except SettingsError as exc:
        print(str(exc))
        raise SystemExit(1) from exc

    configure_logging(settings.log_level)
    logger.info(
        "Starting HT-Manager bot (guild_id=%s, retention_days=%s)",
        settings.discord_guild_id,
        settings.ctf_resource_retention_days,
    )
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
