from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.common.models import Coin, TokenInfo, TokenSource, TokenType
from app.main import app

ADDRESS = "EPeUFDgHRxs9xxEPVaL6kfGQvCon7jmAWKVUHuux1Tpz"


@pytest.fixture
def client():
    return TestClient(app)


def test_get_token_returns_404_when_not_in_registry(client):
    with patch(
        "app.api.tokens.routes.TokenManager.get",
        new=AsyncMock(return_value=None),
    ):
        response = client.get(
            "/api/tokens/v1/get",
            params={"coin": "SOL", "chain_id": "0x65", "address": ADDRESS},
        )

    assert response.status_code == 404


def test_get_token_returns_token_when_present(client):
    token = TokenInfo(
        coin=Coin.SOL,
        chain_id="0x65",
        address=ADDRESS,
        name="Basic Attention Token (Portal)",
        symbol="BAT",
        decimals=8,
        sources=[TokenSource.COINGECKO],
        token_type=TokenType.SPL_TOKEN,
    )

    with patch(
        "app.api.tokens.routes.TokenManager.get",
        new=AsyncMock(return_value=token),
    ):
        response = client.get(
            "/api/tokens/v1/get",
            params={"coin": "SOL", "chain_id": "0x65", "address": ADDRESS},
        )

    assert response.status_code == 200
    assert response.json()["symbol"] == "BAT"
    assert response.json()["token_type"] == "SPL_TOKEN"
