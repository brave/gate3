from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.common.models import Chain
from app.api.pricing.models import (
    BatchTokenPriceRequests,
    CacheStatus,
    CoingeckoPlatform,
    PriceSource,
    TokenPriceRequest,
    TokenPriceResponse,
    VsCurrency,
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
        client.filter = AsyncMock()
        yield client


@pytest.fixture
def mock_jupiter_client():
    with patch("app.api.pricing.routes.JupiterClient") as mock:
        client = mock.return_value
        client.get_prices = AsyncMock()
        client.filter = AsyncMock()
        yield client


@pytest.fixture
def mock_token_price_cache():
    with patch("app.api.pricing.coingecko.CoingeckoPriceCache") as mock:
        mock.get = AsyncMock()
        mock.set = AsyncMock()
        yield mock


def test_get_price_success(client, mock_coingecko_client):
    request = TokenPriceRequest(
        coin_type=Chain.ETHEREUM.coin,
        chain_id=Chain.ETHEREUM.chain_id,
        address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        vs_currency=VsCurrency.USD,
    )
    batch = BatchTokenPriceRequests(requests=[request], vs_currency=VsCurrency.USD)
    empty_batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)

    # Setup mock response
    expected_response = TokenPriceResponse(
        coin_type=Chain.ETHEREUM.coin,
        chain_id=Chain.ETHEREUM.chain_id,
        address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        vs_currency=VsCurrency.USD,
        price=1.01,
        cache_status=CacheStatus.MISS,
        source=PriceSource.COINGECKO,
    )
    mock_coingecko_client.filter.return_value = (batch, empty_batch)
    mock_coingecko_client.get_prices.return_value = [expected_response]

    # Make request
    response = client.get(
        "/api/pricing/v1/getPrice",
        params={
            "coin_type": Chain.ETHEREUM.coin.value,
            "chain_id": Chain.ETHEREUM.chain_id,
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
    assert batch.requests[0] == request


def test_get_price_not_found(client, mock_coingecko_client):
    # Setup mock to return empty list
    request = TokenPriceRequest(
        coin_type=Chain.ETHEREUM.coin,
        chain_id=Chain.ETHEREUM.chain_id,
        address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        vs_currency=VsCurrency.USD,
    )
    empty_batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    mock_coingecko_client.filter.return_value = (
        empty_batch,
        BatchTokenPriceRequests(requests=[request], vs_currency=VsCurrency.USD),
    )
    mock_coingecko_client.get_prices.return_value = []

    # Make request
    response = client.get(
        "/api/pricing/v1/getPrice",
        params={
            "coin_type": Chain.ETHEREUM.coin.value,
            "chain_id": Chain.ETHEREUM.chain_id,
            "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "vs_currency": VsCurrency.USD.value,
        },
    )

    # Verify response
    assert response.status_code == 404
    assert response.json() == {"detail": "Token price not found"}


def test_get_prices_success(client, mock_coingecko_client, mock_jupiter_client):
    request_eth = TokenPriceRequest(
        coin_type=Chain.ETHEREUM.coin,
        chain_id=Chain.ETHEREUM.chain_id,
        address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        vs_currency=VsCurrency.USD,
    )
    request_btc = TokenPriceRequest(
        coin_type=Chain.BITCOIN.coin,
        chain_id=Chain.BITCOIN.chain_id,
        vs_currency=VsCurrency.USD,
    )
    request_sol = TokenPriceRequest(
        coin_type=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="5rmx75XP4VkWcxYsmcLSRbbwzN8g2Cy4YDgBabvboop",
        vs_currency=VsCurrency.EUR,
    )

    # Setup mock response
    response_eth = TokenPriceResponse(
        coin_type=Chain.ETHEREUM.coin,
        chain_id=Chain.ETHEREUM.chain_id,
        address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        vs_currency=VsCurrency.USD,
        price=1.01,
        cache_status=CacheStatus.MISS,
        source=PriceSource.COINGECKO,
    )
    response_btc = TokenPriceResponse(
        coin_type=Chain.BITCOIN.coin,
        chain_id=Chain.BITCOIN.chain_id,
        vs_currency=VsCurrency.USD,
        price=50000.0,
        cache_status=CacheStatus.MISS,
        source=PriceSource.COINGECKO,
    )
    response_sol = TokenPriceResponse(
        coin_type=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="5rmx75XP4VkWcxYsmcLSRbbwzN8g2Cy4YDgBabvboop",
        vs_currency=VsCurrency.EUR,
        price=0.0000283013301,
        cache_status=CacheStatus.MISS,
        source=PriceSource.JUPITER,
    )
    mock_coingecko_client.filter.return_value = (
        BatchTokenPriceRequests(
            requests=[request_eth, request_btc], vs_currency=VsCurrency.USD
        ),
        BatchTokenPriceRequests(requests=[request_sol], vs_currency=VsCurrency.EUR),
    )
    mock_jupiter_client.filter.return_value = (
        BatchTokenPriceRequests(requests=[request_sol], vs_currency=VsCurrency.EUR),
        BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD),
    )
    mock_coingecko_client.get_prices.return_value = [
        response_eth,
        response_btc,
    ]
    mock_jupiter_client.get_prices.return_value = [
        response_sol,
    ]

    # Make request
    response = client.post(
        "/api/pricing/v1/getPrices",
        params={"vs_currency": VsCurrency.USD.value},
        json=[
            {
                "coin_type": Chain.ETHEREUM.coin.value,
                "chain_id": Chain.ETHEREUM.chain_id,
                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            },
            {
                "coin_type": Chain.BITCOIN.coin.value,
                "chain_id": Chain.BITCOIN.chain_id,
            },
        ],
    )

    # Verify response
    assert response.status_code == 200
    assert response.json() == [
        response_eth.model_dump(),
        response_btc.model_dump(),
        response_sol.model_dump(),
    ]

    # Verify mock was called correctly
    mock_coingecko_client.get_prices.assert_called_once()
    batch = mock_coingecko_client.get_prices.call_args[0][0]
    assert len(batch.requests) == 2
    assert batch.requests[0] == request_eth
    assert batch.requests[1] == request_btc
    assert batch.vs_currency == VsCurrency.USD
    mock_jupiter_client.get_prices.assert_called_once()
    kwargs = mock_jupiter_client.get_prices.call_args[1]
    assert kwargs["coingecko_client"] is mock_coingecko_client
    batch = kwargs["batch"]
    assert len(batch.requests) == 1
    assert batch.requests[0] == request_sol
    assert batch.vs_currency == VsCurrency.EUR


def test_get_prices_empty_list(client, mock_coingecko_client, mock_jupiter_client):
    # Setup mock to return empty list
    empty_batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    mock_coingecko_client.filter.return_value = (
        empty_batch,
        empty_batch,
    )
    mock_jupiter_client.filter.return_value = (
        empty_batch,
        empty_batch,
    )

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
    # Patch all cache get/set methods to prevent Redis connections
    with (
        patch(
            "app.api.pricing.coingecko.PlatformMapCache.get", new_callable=AsyncMock
        ) as mock_platform_cache_get,
        patch("app.api.pricing.coingecko.PlatformMapCache.set", new_callable=AsyncMock),
        patch(
            "app.api.pricing.coingecko.CoinMapCache.get", new_callable=AsyncMock
        ) as mock_coin_cache_get,
        patch("app.api.pricing.coingecko.CoinMapCache.set", new_callable=AsyncMock),
        patch(
            "app.api.pricing.coingecko.CoingeckoPriceCache.get", new_callable=AsyncMock
        ) as mock_cache_get,
        patch(
            "app.api.pricing.coingecko.CoingeckoPriceCache.set", new_callable=AsyncMock
        ),
    ):
        cached_response = TokenPriceResponse(
            coin_type=Chain.ETHEREUM.coin,
            chain_id=Chain.ETHEREUM.chain_id,
            address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            vs_currency=VsCurrency.USD,
            price=1.01,
            cache_status=CacheStatus.HIT,
            source=PriceSource.COINGECKO,
        )

        # Mock the cache to return the cached response and an empty batch to fetch
        mock_cache_get.return_value = (
            [cached_response],
            BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD),
        )
        mock_platform_cache_get.return_value = {
            "ethereum": CoingeckoPlatform(
                id="ethereum",
                chain_id=Chain.ETHEREUM.chain_id,
                native_token_id="ethereum",
            ),
        }
        mock_coin_cache_get.return_value = {
            Chain.ETHEREUM.chain_id: {
                "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "usd-coin",
            },
        }

        response = client.get(
            "/api/pricing/v1/getPrice",
            params={
                "coin_type": Chain.ETHEREUM.coin.value,
                "chain_id": Chain.ETHEREUM.chain_id,
                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "vs_currency": VsCurrency.USD.value,
            },
        )

        assert response.status_code == 200
        assert response.json() == cached_response.model_dump()
        mock_cache_get.assert_called_once()
        mock_platform_cache_get.assert_called_once()
        mock_coin_cache_get.assert_called_once()
