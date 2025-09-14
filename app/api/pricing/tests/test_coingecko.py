from unittest.mock import AsyncMock, patch

import pytest

from app.api.common.models import Chain
from app.api.pricing.coingecko import CoinGeckoClient
from app.api.pricing.models import (
    BatchTokenPriceRequests,
    TokenPriceRequest,
    VsCurrency,
)


@pytest.fixture
def client():
    return CoinGeckoClient()


@pytest.fixture
def mock_httpx_client():
    with patch("httpx.AsyncClient") as mock:
        mock_client = AsyncMock()
        mock.return_value.__aenter__.return_value = mock_client
        yield mock_client


@pytest.mark.asyncio
async def test_get_prices_chunking(client, mock_httpx_client):
    # Create a batch with 7 requests (should create 3 chunks: 3, 3, 1)
    requests = [
        TokenPriceRequest(
            chain_id=Chain.ETHEREUM.chain_id,
            address=f"0x{i}",
            coin_type=Chain.ETHEREUM.coin,
        )
        for i in range(7)
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    with (
        patch("app.api.pricing.coingecko.CoingeckoPriceCache.get") as mock_cache,
        patch(
            "app.api.pricing.coingecko.CoingeckoPriceCache.set", new_callable=AsyncMock
        ),
        patch.object(client, "get_platform_map") as mock_platform_map,
        patch.object(client, "get_coin_map") as mock_coin_map,
        patch("app.api.pricing.coingecko.COINGECKO_CHUNK_SIZE", 3),
    ):
        mock_cache.return_value = ([], batch)

        mock_platform_map.return_value = {"ethereum": {"chain_id": "0x1"}}
        mock_coin_map.return_value = {"0x1": {f"0x{i}": f"token{i}" for i in range(7)}}

        # Mock the HTTP response
        mock_response = AsyncMock()
        mock_response.json = lambda: {
            f"token{i}": {"usd": 1.0, "usd_24h_change": 2.5} for i in range(7)
        }
        mock_response.raise_for_status = lambda: None
        mock_httpx_client.get.return_value = mock_response

        # Call get_prices
        results = await client.get_prices(batch)

        # Verify the number of HTTP requests made (should be 3 chunks)
        assert mock_httpx_client.get.call_count == 3

        # Verify the results
        assert len(results) == 7
        for result in results:
            assert result.price == 1.0
            assert result.cache_status == "MISS"
