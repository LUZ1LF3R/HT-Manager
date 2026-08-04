from sqlalchemy import text


async def test_db_session_can_execute_query(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
