import pytest


@pytest.mark.asyncio
async def test_ping_reports_redis_ok(client):
    response = await client.get("/api/ping")

    assert response.status_code == 200
    assert response.json() == {"redis": "OK"}
