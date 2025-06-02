import json
import pytest
from unittest.mock import AsyncMock, patch

from app.api.common.models import CoinType, ChainId
from app.api.pricing.cache import TokenPriceCache
from app.api.pricing.models import (
    TokenPriceRequest,
    TokenPriceResponse,
    CacheStatus,
    BatchTokenPriceRequests,
    VsCurrency,
)


@pytest.fixture
def mock_redis():
    with patch("app.api.pricing.cache.Cache.get_client") as mock:
        mock_redis = AsyncMock()
        mock.return_value.__aenter__.return_value = mock_redis
        yield mock_redis


@pytest.mark.asyncio
async def test_get_empty_batch(mock_redis):
    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    cached_responses, batch_to_fetch = await TokenPriceCache.get(batch)

    assert len(cached_responses) == 0
    assert batch_to_fetch.is_empty()
    mock_redis.mget.assert_not_called()


@pytest.mark.asyncio
async def test_get_with_cached_values(mock_redis):
    # Setup test data
    usdc_request = TokenPriceRequest(
        coin_type=CoinType.ETH,
        chain_id=ChainId.ARBITRUM,
        address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        vs_currency=VsCurrency.USD,
    )
    eth_request = TokenPriceRequest(
        coin_type=CoinType.ETH,
        chain_id=ChainId.ETHEREUM,
        address="",
        vs_currency=VsCurrency.USD,
    )
    btc_request = TokenPriceRequest(coin_type=CoinType.BTC, vs_currency=VsCurrency.USD)

    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    batch.add(usdc_request)
    batch.add(eth_request)
    batch.add(btc_request)

    # Mock cached values
    usdc_response = TokenPriceResponse(
        coin_type=CoinType.ETH,
        chain_id=ChainId.ARBITRUM,
        address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        price=1.01,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
    )
    eth_response = TokenPriceResponse(
        coin_type=CoinType.ETH,
        chain_id=ChainId.ETHEREUM,
        address="",
        price=2000.0,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
    )
    btc_response = TokenPriceResponse(
        coin_type=CoinType.BTC,
        price=50000.0,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
    )

    # Create cached data without cache_status
    usdc_data = usdc_response.model_dump(exclude={"cache_status"})
    eth_data = eth_response.model_dump(exclude={"cache_status"})
    btc_data = btc_response.model_dump(exclude={"cache_status"})

    mock_redis.mget.return_value = [
        json.dumps(usdc_data),
        json.dumps(eth_data),
        json.dumps(btc_data),
    ]

    # Test
    cached_responses, batch_to_fetch = await TokenPriceCache.get(batch)

    # Assertions
    assert len(cached_responses) == 3
    assert batch_to_fetch.size() == 0
    assert all(
        response.cache_status == CacheStatus.HIT for response in cached_responses
    )
    assert cached_responses[0].price == 1.01
    assert cached_responses[1].price == 2000.0
    assert cached_responses[2].price == 50000.0

    # Verify cache keys were generated correctly
    mock_redis.mget.assert_called_once()
    called_keys = mock_redis.mget.call_args[0][0]
    assert len(called_keys) == 3
    assert (
        called_keys[0]
        == "price:eth:0xa4b1:0xaf88d065e77c8cc2239327c5edb3a432268e5831:usd"
    )
    assert called_keys[1] == "price:eth:0x1:usd"
    assert called_keys[2] == "price:btc:usd"


@pytest.mark.asyncio
async def test_get_with_mixed_cache_status(mock_redis):
    # Setup test data
    eth_request = TokenPriceRequest(
        coin_type=CoinType.ETH,
        chain_id=ChainId.ARBITRUM,
        address="0x123",
        vs_currency=VsCurrency.USD,
    )
    btc_request = TokenPriceRequest(coin_type=CoinType.BTC, vs_currency=VsCurrency.USD)

    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    batch.add(eth_request)
    batch.add(btc_request)

    # Mock cached values (only ETH is cached)
    eth_response = TokenPriceResponse(
        coin_type=CoinType.ETH,
        chain_id=ChainId.ARBITRUM,
        address="0x123",
        price=2000.0,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
    )

    # Create cached data without cache_status
    eth_data = eth_response.model_dump(exclude={"cache_status"})

    mock_redis.mget.return_value = [json.dumps(eth_data), None]

    # Test
    cached_responses, batch_to_fetch = await TokenPriceCache.get(batch)

    # Assertions
    assert len(cached_responses) == 1
    assert batch_to_fetch.size() == 1
    assert cached_responses[0].coin_type == CoinType.ETH
    assert cached_responses[0].cache_status == CacheStatus.HIT
    assert batch_to_fetch.requests[0].coin_type == CoinType.BTC

    # Verify cache keys were generated correctly
    mock_redis.mget.assert_called_once()
    called_keys = mock_redis.mget.call_args[0][0]
    assert len(called_keys) == 2
    assert called_keys[0] == "price:eth:0xa4b1:0x123:usd"
    assert called_keys[1] == "price:btc:usd"


@pytest.mark.asyncio
async def test_set_multiple_responses(mock_redis):
    # Setup test data
    responses = [
        TokenPriceResponse(
            coin_type=CoinType.ETH,
            chain_id=ChainId.ARBITRUM,
            address="0x123",
            price=2000.0,
            vs_currency=VsCurrency.USD,
            cache_status=CacheStatus.HIT,
        ),
        TokenPriceResponse(
            coin_type=CoinType.BTC,
            price=50000.0,
            vs_currency=VsCurrency.USD,
            cache_status=CacheStatus.HIT,
        ),
    ]

    # Mock pipeline
    mock_pipe = AsyncMock()
    mock_redis.pipeline.return_value = mock_pipe

    # Test
    await TokenPriceCache.set(responses)

    # Assertions
    mock_redis.pipeline.assert_called_once()

    # Verify setex was called with correct keys and values
    assert mock_pipe.setex.call_count == 2
    setex_calls = mock_pipe.setex.call_args_list

    # Check ETH token cache
    eth_call = setex_calls[0]
    assert eth_call[0][0] == "price:eth:0xa4b1:0x123:usd"  # key
    assert eth_call[0][1] == TokenPriceCache.DEFAULT_TTL  # ttl
    eth_data = json.loads(eth_call[0][2])  # value
    assert eth_data["price"] == 2000.0
    assert eth_data["coin_type"] == "ETH"
    assert "cache_status" not in eth_data  # cache_status should be excluded

    # Check BTC token cache
    btc_call = setex_calls[1]
    assert btc_call[0][0] == "price:btc:usd"  # key
    assert btc_call[0][1] == TokenPriceCache.DEFAULT_TTL  # ttl
    btc_data = json.loads(btc_call[0][2])  # value
    assert btc_data["price"] == 50000.0
    assert btc_data["coin_type"] == "BTC"
    assert "cache_status" not in btc_data  # cache_status should be excluded

    # Verify pipeline was closed
    mock_pipe.aclose.assert_called_once()
    mock_pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_set_empty_responses(mock_redis):
    await TokenPriceCache.set([])
    mock_redis.pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_set_with_custom_ttl(mock_redis):
    custom_ttl = 120
    response = TokenPriceResponse(
        coin_type=CoinType.ETH,
        chain_id=ChainId.ARBITRUM,
        address="0x123",
        price=2000.0,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
    )

    # Mock pipeline
    mock_pipe = AsyncMock()
    mock_redis.pipeline.return_value = mock_pipe

    await TokenPriceCache.set([response], ttl=custom_ttl)

    # Verify setex was called with correct ttl
    setex_call = mock_pipe.setex.call_args[0]
    assert setex_call[1] == custom_ttl  # ttl

    # Verify pipeline was closed
    mock_pipe.aclose.assert_called_once()
    mock_pipe.execute.assert_called_once()
