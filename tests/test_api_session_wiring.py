import httpx
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ht_manager.api.dependencies import get_session


async def test_api_get_session_override_is_isolated_and_usable(
    api_app: FastAPI, api_client: httpx.AsyncClient
) -> None:
    """Proves the api_client/api_app fixtures actually route a DB-touching
    request through the isolated session factory — not just that they
    register an override, but that a real request can use it without
    hitting the cross-event-loop bug a synchronous TestClient would."""

    @api_app.get("/_test_dbcheck")
    async def dbcheck(session: AsyncSession = Depends(get_session)) -> dict[str, int]:
        result = await session.execute(text("SELECT 1"))
        return {"value": result.scalar_one()}

    response = await api_client.get("/_test_dbcheck")

    assert response.status_code == 200
    assert response.json() == {"value": 1}
