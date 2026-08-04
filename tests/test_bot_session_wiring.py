from sqlalchemy import text

from ht_manager.bot.client import HTManagerBot


async def test_bot_session_factory_can_execute_query(bot: HTManagerBot) -> None:
    async with bot.session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
