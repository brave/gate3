from unittest.mock import AsyncMock, patch

import httpx
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
            coin=Chain.ETHEREUM.coin,
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


@pytest.mark.sanity
@pytest.mark.asyncio
async def test_vs_currency_enum_entries_valid():
    """
    Validate that our VsCurrency enum entries are supported by CoinGecko API.
    This test makes a real API call to ensure our enum stays in sync with CoinGecko.
    If this fails, it means CoinGecko removed support for a currency we're using.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.coingecko.com/api/v3/simple/supported_vs_currencies"
        )
        response.raise_for_status()
        supported_currencies = {currency.upper() for currency in response.json()}

    # Get our enum values
    our_currencies = {currency.value for currency in VsCurrency}

    # Check if all our currencies are supported by CoinGecko
    unsupported = our_currencies - supported_currencies
    assert not unsupported, (
        f"VsCurrency enum contains currencies not supported by CoinGecko API: {unsupported}. "
        f"Either remove these from the enum or verify CoinGecko still supports them."
    )
