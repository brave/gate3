from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.common.models import Chain
from app.api.pricing.jupiter import JupiterClient
from app.api.pricing.models import (
    BatchTokenPriceRequests,
    CacheStatus,
    PriceSource,
    TokenPriceRequest,
    TokenPriceResponse,
    VsCurrency,
)


@pytest.fixture
def client():
    return JupiterClient()


@pytest.fixture
def mock_httpx_client():
    with patch("httpx.AsyncClient") as mock:
        mock_client = AsyncMock()
        mock.return_value.__aenter__.return_value = mock_client
        yield mock_client


@pytest.mark.asyncio
async def test_filter_solana_tokens(client):
    # Create a batch with mixed token types
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            coin_type=Chain.SOLANA.coin,
        ),
        TokenPriceRequest(
            chain_id=Chain.ETHEREUM.chain_id,
            address="0x123",
            coin_type=Chain.ETHEREUM.coin,
        ),
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="So11111111111111111111111111111111111111112",
            coin_type=Chain.SOLANA.coin,
        ),
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address=None,  # No address
            coin_type=Chain.SOLANA.coin,
        ),
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    available_batch, unavailable_batch = await client.filter(batch)

    assert len(available_batch.requests) == 2
    assert available_batch.requests[0] == requests[0]
    assert available_batch.requests[1] == requests[2]
    assert len(unavailable_batch.requests) == 2
    assert unavailable_batch.requests[0] == requests[1]
    assert unavailable_batch.requests[1] == requests[3]


@pytest.mark.asyncio
async def test_get_prices_empty_batch(client):
    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    results = await client.get_prices(batch=batch, coingecko_client=MagicMock())
    assert results == []


@pytest.mark.asyncio
async def test_get_prices_all_cached(client):
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            coin_type=Chain.SOLANA.coin,
        ),
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    cached_response = TokenPriceResponse(
        chain_id=Chain.SOLANA.chain_id,
        address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        coin_type=Chain.SOLANA.coin,
        vs_currency=VsCurrency.USD,
        price=1.0,
        cache_status=CacheStatus.HIT,
        source=PriceSource.JUPITER,
    )

    with patch("app.api.pricing.jupiter.JupiterPriceCache.get") as mock_cache:
        mock_cache.return_value = (
            [cached_response],
            BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD),
        )

        results = await client.get_prices(batch=batch, coingecko_client=MagicMock())

        assert len(results) == 1
        assert results[0].price == 1.0
        assert results[0].cache_status == CacheStatus.HIT


@pytest.mark.asyncio
async def test_get_prices_chunking(client, mock_httpx_client):
    # Create a batch with 7 requests (should create 2 chunks: 5, 2 with default chunk size of 50)
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address=f"address{i}",
            coin_type=Chain.SOLANA.coin,
        )
        for i in range(7)
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    with (
        patch("app.api.pricing.jupiter.JupiterPriceCache.get") as mock_cache,
        patch("app.api.pricing.jupiter.JupiterPriceCache.set", new_callable=AsyncMock),
        patch(
            "app.api.pricing.jupiter.JUPITER_CHUNK_SIZE", 5
        ),  # Override chunk size for testing
    ):
        mock_cache.return_value = ([], batch)

        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {f"address{i}": {"price": "1.0"} for i in range(7)}
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.get.return_value = mock_response

        # Call get_prices
        results = await client.get_prices(batch=batch, coingecko_client=MagicMock())

        # Verify the number of HTTP requests made (should be 2 chunks)
        assert mock_httpx_client.get.call_count == 2

        # Verify the results
        assert len(results) == 7
        for result in results:
            assert result.price == 1.0
            assert result.cache_status == CacheStatus.MISS


@pytest.mark.asyncio
async def test_get_prices_usd_currency(client, mock_httpx_client):
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            coin_type=Chain.SOLANA.coin,
        ),
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    with (
        patch("app.api.pricing.jupiter.JupiterPriceCache.get") as mock_cache,
        patch("app.api.pricing.jupiter.JupiterPriceCache.set", new_callable=AsyncMock),
    ):
        mock_cache.return_value = ([], batch)

        # Mock Jupiter API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {"price": "1.0"}}
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.get.return_value = mock_response

        results = await client.get_prices(batch=batch, coingecko_client=MagicMock())

        # Verify HTTP request was made (now with chunking, it might be called multiple times)
        mock_httpx_client.get.assert_called()
        # Check that at least one call was made with the expected parameters
        call_args_list = mock_httpx_client.get.call_args_list
        assert any(
            call[0][0] == "https://lite-api.jup.ag/price/v2"
            and call[1]["params"]["ids"]
            == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            for call in call_args_list
        )

        # Verify results
        assert len(results) == 1
        assert results[0].price == 1.0
        assert results[0].cache_status == CacheStatus.MISS


@pytest.mark.asyncio
async def test_get_prices_non_usd_currency(client, mock_httpx_client):
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="5rmx75XP4VkWcxYsmcLSRbbwzN8g2Cy4YDgBabvboop",  # $PUMP
            coin_type=Chain.SOLANA.coin,
        ),
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.EUR)

    mock_coingecko_client = AsyncMock()
    mock_coingecko_client.get_prices.return_value = [
        TokenPriceResponse(
            chain_id=Chain.SOLANA.chain_id,
            address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            coin_type=Chain.SOLANA.coin,
            vs_currency=VsCurrency.EUR,
            price=0.85,  # USDC price in EUR
            cache_status=CacheStatus.MISS,
            source=PriceSource.COINGECKO,
        )
    ]

    with (
        patch("app.api.pricing.jupiter.JupiterPriceCache.get") as mock_cache,
        patch("app.api.pricing.jupiter.JupiterPriceCache.set", new_callable=AsyncMock),
    ):
        mock_cache.return_value = ([], batch)

        # Mock Jupiter API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "5rmx75XP4VkWcxYsmcLSRbbwzN8g2Cy4YDgBabvboop": {
                    "price": "10.0"
                }  # $PUMP price in USDC
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.get.return_value = mock_response

        results = await client.get_prices(batch, coingecko_client=mock_coingecko_client)

        # Verify USDC price was fetched for conversion
        mock_coingecko_client.get_prices.assert_called_once()
        usdc_batch = mock_coingecko_client.get_prices.call_args[0][0]
        assert usdc_batch.vs_currency == VsCurrency.EUR
        assert len(usdc_batch.requests) == 1
        assert (
            usdc_batch.requests[0].address
            == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )

        # Verify price was converted (10.0 * 0.85 = 8.5)
        assert len(results) == 1
        assert results[0].price == 8.5  # $PUMP price in EUR
        assert results[0].cache_status == CacheStatus.MISS


@pytest.mark.asyncio
async def test_get_prices_missing_addresses(client, mock_httpx_client):
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address=None,  # No address
            coin_type=Chain.SOLANA.coin,
        ),
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    with patch("app.api.pricing.jupiter.JupiterPriceCache.get") as mock_cache:
        mock_cache.return_value = ([], batch)

        results = await client.get_prices(batch=batch, coingecko_client=MagicMock())

        # Should return empty results without making HTTP request
        assert results == []
        mock_httpx_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_prices_http_error(client, mock_httpx_client):
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            coin_type=Chain.SOLANA.coin,
        ),
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    with (
        patch("app.api.pricing.jupiter.JupiterPriceCache.get") as mock_cache,
        patch("app.api.pricing.jupiter.JupiterPriceCache.set", new_callable=AsyncMock),
    ):
        mock_cache.return_value = ([], batch)

        # Mock HTTP error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_httpx_client.get.return_value = mock_response

        # With chunking and return_exceptions=True, HTTP errors are handled gracefully
        # and don't raise exceptions - they just result in empty results
        results = await client.get_prices(batch=batch, coingecko_client=MagicMock())

        # Should return empty results when HTTP errors occur
        assert results == []


@pytest.mark.asyncio
async def test_get_prices_invalid_price_data(client, mock_httpx_client):
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            coin_type=Chain.SOLANA.coin,
        ),
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="So11111111111111111111111111111111111111112",
            coin_type=Chain.SOLANA.coin,
        ),
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    with (
        patch("app.api.pricing.jupiter.JupiterPriceCache.get") as mock_cache,
        patch("app.api.pricing.jupiter.JupiterPriceCache.set", new_callable=AsyncMock),
    ):
        mock_cache.return_value = ([], batch)

        # Mock Jupiter API response with invalid data
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {
                    "price": "invalid"
                },  # Invalid price
                "So11111111111111111111111111111111111111112": {
                    "price": "1.5"
                },  # Valid price
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.get.return_value = mock_response

        results = await client.get_prices(batch=batch, coingecko_client=MagicMock())

        # Should only return the valid price
        assert len(results) == 1
        assert results[0].address == "So11111111111111111111111111111111111111112"
        assert results[0].price == 1.5


@pytest.mark.asyncio
async def test_get_prices_missing_token_in_response(client, mock_httpx_client):
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            coin_type=Chain.SOLANA.coin,
        ),
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="So11111111111111111111111111111111111111112",
            coin_type=Chain.SOLANA.coin,
        ),
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    with (
        patch("app.api.pricing.jupiter.JupiterPriceCache.get") as mock_cache,
        patch("app.api.pricing.jupiter.JupiterPriceCache.set", new_callable=AsyncMock),
    ):
        mock_cache.return_value = ([], batch)

        # Mock Jupiter API response with missing token
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {
                    "price": "1.0"
                },  # Present
                # "So11111111111111111111111111111111111111112" is missing
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.get.return_value = mock_response

        results = await client.get_prices(batch=batch, coingecko_client=MagicMock())

        # Should only return the token that was present in response
        assert len(results) == 1
        assert results[0].address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        assert results[0].price == 1.0


@pytest.mark.asyncio
async def test_get_prices_mixed_cache_and_fetch(client, mock_httpx_client):
    requests = [
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            coin_type=Chain.SOLANA.coin,
        ),
        TokenPriceRequest(
            chain_id=Chain.SOLANA.chain_id,
            address="So11111111111111111111111111111111111111112",
            coin_type=Chain.SOLANA.coin,
        ),
    ]
    batch = BatchTokenPriceRequests(requests=requests, vs_currency=VsCurrency.USD)

    # Cached response
    cached_response = TokenPriceResponse(
        chain_id=Chain.SOLANA.chain_id,
        address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        coin_type=Chain.SOLANA.coin,
        vs_currency=VsCurrency.USD,
        price=1.0,
        cache_status=CacheStatus.HIT,
        source=PriceSource.JUPITER,
    )

    # Batch to fetch
    fetch_batch = BatchTokenPriceRequests(
        requests=[requests[1]], vs_currency=VsCurrency.USD
    )

    with (
        patch("app.api.pricing.jupiter.JupiterPriceCache.get") as mock_cache,
        patch("app.api.pricing.jupiter.JupiterPriceCache.set", new_callable=AsyncMock),
    ):
        mock_cache.return_value = ([cached_response], fetch_batch)

        # Mock Jupiter API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"So11111111111111111111111111111111111111112": {"price": "2.0"}}
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.get.return_value = mock_response

        results = await client.get_prices(batch=batch, coingecko_client=MagicMock())

        # Should return both cached and fetched results
        assert len(results) == 2

        # Find cached result
        cached_result = next(
            r
            for r in results
            if r.address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        )
        assert cached_result.price == 1.0
        assert cached_result.cache_status == CacheStatus.HIT

        # Find fetched result
        fetched_result = next(
            r
            for r in results
            if r.address == "So11111111111111111111111111111111111111112"
        )
        assert fetched_result.price == 2.0
        assert fetched_result.cache_status == CacheStatus.MISS
