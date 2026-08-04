import httpx


async def test_health_returns_ok(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
