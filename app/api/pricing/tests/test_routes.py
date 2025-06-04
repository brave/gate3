import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.common.models import ChainId, CoinType
from app.api.pricing.models import (
    TokenPriceResponse,
    VsCurrency,
    CacheStatus,
    BatchTokenPriceRequests,
)

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_coingecko_client():
    with patch("app.api.pricing.routes.CoinGeckoClient") as mock:
        client = mock.return_value
        client.get_prices = AsyncMock()
        yield client


@pytest.fixture
def mock_token_price_cache():
    with patch("app.api.pricing.coingecko.TokenPriceCache") as mock:
        mock.get = AsyncMock()
        mock.set = AsyncMock()
        yield mock


def test_get_price_success(client, mock_coingecko_client):
    # Setup mock response
    expected_response = TokenPriceResponse(
        coin_type=CoinType.ETH,
        chain_id=ChainId.ETHEREUM,
        address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        vs_currency=VsCurrency.USD,
        price=1.01,
        cache_status=CacheStatus.MISS,
    )
    mock_coingecko_client.get_prices.return_value = [expected_response]

    # Make request
    response = client.get(
        "/api/pricing/v1/getPrice",
        params={
            "coin_type": CoinType.ETH.value,
            "chain_id": ChainId.ETHEREUM.value,
            "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "vs_currency": VsCurrency.USD.value,
        },
    )

    # Verify response
    assert response.status_code == 200
    assert response.json() == expected_response.model_dump()

    # Verify mock was called correctly
    mock_coingecko_client.get_prices.assert_called_once()
    batch = mock_coingecko_client.get_prices.call_args[0][0]
    assert len(batch.requests) == 1
    assert batch.requests[0].coin_type == CoinType.ETH
    assert batch.requests[0].chain_id == ChainId.ETHEREUM
    assert batch.requests[0].address == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    assert batch.vs_currency == VsCurrency.USD


def test_get_price_not_found(client, mock_coingecko_client):
    # Setup mock to return empty list
    mock_coingecko_client.get_prices.return_value = []

    # Make request
    response = client.get(
        "/api/pricing/v1/getPrice",
        params={
            "coin_type": CoinType.ETH.value,
            "chain_id": ChainId.ETHEREUM.value,
            "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "vs_currency": VsCurrency.USD.value,
        },
    )

    # Verify response
    assert response.status_code == 404
    assert response.json() == {"detail": "Token price not found"}


def test_get_prices_success(client, mock_coingecko_client):
    # Setup mock response
    expected_responses = [
        TokenPriceResponse(
            coin_type=CoinType.ETH,
            chain_id=ChainId.ETHEREUM,
            address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            vs_currency=VsCurrency.USD,
            price=1.01,
            cache_status=CacheStatus.MISS,
        ),
        TokenPriceResponse(
            coin_type=CoinType.BTC,
            vs_currency=VsCurrency.USD,
            price=50000.0,
            cache_status=CacheStatus.MISS,
        ),
    ]
    mock_coingecko_client.get_prices.return_value = expected_responses

    # Make request
    response = client.post(
        "/api/pricing/v1/getPrices",
        params={"vs_currency": VsCurrency.USD.value},
        json=[
            {
                "coin_type": CoinType.ETH.value,
                "chain_id": ChainId.ETHEREUM.value,
                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            },
            {"coin_type": CoinType.BTC.value},
        ],
    )

    # Verify response
    assert response.status_code == 200
    assert response.json() == [resp.model_dump() for resp in expected_responses]

    # Verify mock was called correctly
    mock_coingecko_client.get_prices.assert_called_once()
    batch = mock_coingecko_client.get_prices.call_args[0][0]
    assert len(batch.requests) == 2
    assert batch.requests[0].coin_type == CoinType.ETH
    assert batch.requests[1].coin_type == CoinType.BTC
    assert batch.vs_currency == VsCurrency.USD


def test_get_prices_empty_list(client, mock_coingecko_client):
    # Setup mock to return empty list
    mock_coingecko_client.get_prices.return_value = []

    # Make request
    response = client.post(
        "/api/pricing/v1/getPrices",
        params={"vs_currency": VsCurrency.USD.value},
        json=[],
    )

    # Verify response
    assert response.status_code == 200
    assert response.json() == []


def test_get_price_cached_response(client):
    # Patch TokenPriceCache.get in the correct place
    with patch(
        "app.api.pricing.coingecko.TokenPriceCache.get", new_callable=AsyncMock
    ) as mock_cache_get:
        cached_response = TokenPriceResponse(
            coin_type=CoinType.ETH,
            chain_id=ChainId.ETHEREUM,
            address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            vs_currency=VsCurrency.USD,
            price=1.01,
            cache_status=CacheStatus.HIT,
        )
        mock_cache_get.return_value = (
            [cached_response],
            BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD),
        )

        response = client.get(
            "/api/pricing/v1/getPrice",
            params={
                "coin_type": CoinType.ETH.value,
                "chain_id": ChainId.ETHEREUM.value,
                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "vs_currency": VsCurrency.USD.value,
            },
        )

        assert response.status_code == 200
        assert response.json() == cached_response.model_dump()
        mock_cache_get.assert_called_once()
