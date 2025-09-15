import json
from unittest.mock import AsyncMock, patch

import pytest

from app.api.common.models import Chain
from app.api.pricing.cache import CoingeckoPriceCache, JupiterPriceCache
from app.api.pricing.models import (
    BatchTokenPriceRequests,
    CacheStatus,
    PriceSource,
    TokenPriceRequest,
    TokenPriceResponse,
    VsCurrency,
)


@pytest.fixture
def mock_redis():
    with patch("app.api.pricing.cache.Cache.get_client") as mock:
        mock_redis = AsyncMock()
        mock.return_value.__aenter__.return_value = mock_redis
        yield mock_redis


@pytest.mark.asyncio
async def test_coingecko_get_empty_batch(mock_redis):
    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    cached_responses, batch_to_fetch = await CoingeckoPriceCache.get(batch)

    assert len(cached_responses) == 0
    assert batch_to_fetch.is_empty()
    mock_redis.mget.assert_not_called()


@pytest.mark.asyncio
async def test_coingecko_get_with_cached_values(mock_redis):
    # Setup test data
    usdc_request = TokenPriceRequest(
        coin=Chain.ARBITRUM.coin,
        chain_id=Chain.ARBITRUM.chain_id,
        address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        vs_currency=VsCurrency.USD,
    )
    eth_request = TokenPriceRequest(
        coin=Chain.ETHEREUM.coin,
        chain_id=Chain.ETHEREUM.chain_id,
        address="",
        vs_currency=VsCurrency.USD,
    )
    btc_request = TokenPriceRequest(
        coin=Chain.BITCOIN.coin,
        chain_id=Chain.BITCOIN.chain_id,
        vs_currency=VsCurrency.USD,
    )

    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    batch.add(usdc_request)
    batch.add(eth_request)
    batch.add(btc_request)

    # Mock cached values
    usdc_response = TokenPriceResponse(
        coin=Chain.ARBITRUM.coin,
        chain_id=Chain.ARBITRUM.chain_id,
        address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        price=1.01,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.COINGECKO,
    )
    eth_response = TokenPriceResponse(
        coin=Chain.ETHEREUM.coin,
        chain_id=Chain.ETHEREUM.chain_id,
        address="",
        price=2000.0,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.COINGECKO,
    )
    btc_response = TokenPriceResponse(
        coin=Chain.BITCOIN.coin,
        chain_id=Chain.BITCOIN.chain_id,
        price=50000.0,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.COINGECKO,
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
    cached_responses, batch_to_fetch = await CoingeckoPriceCache.get(batch)

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
        == "coingecko:price:eth:0xa4b1:0xaf88d065e77c8cc2239327c5edb3a432268e5831:usd"
    )
    assert called_keys[1] == "coingecko:price:eth:0x1:usd"
    assert called_keys[2] == "coingecko:price:btc:bitcoin_mainnet:usd"


@pytest.mark.asyncio
async def test_coingecko_get_with_mixed_cache_status(mock_redis):
    # Setup test data
    eth_request = TokenPriceRequest(
        coin=Chain.ARBITRUM.coin,
        chain_id=Chain.ARBITRUM.chain_id,
        address="0x123",
        vs_currency=VsCurrency.USD,
    )
    btc_request = TokenPriceRequest(
        coin=Chain.BITCOIN.coin,
        chain_id=Chain.BITCOIN.chain_id,
        vs_currency=VsCurrency.USD,
    )

    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    batch.add(eth_request)
    batch.add(btc_request)

    # Mock cached values (only ETH is cached)
    eth_response = TokenPriceResponse(
        coin=Chain.ARBITRUM.coin,
        chain_id=Chain.ARBITRUM.chain_id,
        address="0x123",
        price=2000.0,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.COINGECKO,
    )

    # Create cached data without cache_status
    eth_data = eth_response.model_dump(exclude={"cache_status"})

    mock_redis.mget.return_value = [json.dumps(eth_data), None]

    # Test
    cached_responses, batch_to_fetch = await CoingeckoPriceCache.get(batch)

    # Assertions
    assert len(cached_responses) == 1
    assert batch_to_fetch.size() == 1
    assert cached_responses[0].coin == Chain.ARBITRUM.coin
    assert cached_responses[0].cache_status == CacheStatus.HIT
    assert batch_to_fetch.requests[0].coin == Chain.BITCOIN.coin

    # Verify cache keys were generated correctly
    mock_redis.mget.assert_called_once()
    called_keys = mock_redis.mget.call_args[0][0]
    assert len(called_keys) == 2
    assert called_keys[0] == "coingecko:price:eth:0xa4b1:0x123:usd"
    assert called_keys[1] == "coingecko:price:btc:bitcoin_mainnet:usd"


@pytest.mark.asyncio
async def test_coingecko_set_multiple_responses(mock_redis):
    # Setup test data
    responses = [
        TokenPriceResponse(
            coin=Chain.ARBITRUM.coin,
            chain_id=Chain.ARBITRUM.chain_id,
            address="0x123",
            price=2000.0,
            vs_currency=VsCurrency.USD,
            cache_status=CacheStatus.HIT,
            source=PriceSource.COINGECKO,
        ),
        TokenPriceResponse(
            coin=Chain.BITCOIN.coin,
            chain_id=Chain.BITCOIN.chain_id,
            price=50000.0,
            vs_currency=VsCurrency.USD,
            cache_status=CacheStatus.HIT,
            source=PriceSource.COINGECKO,
        ),
    ]

    # Mock pipeline
    mock_pipe = AsyncMock()
    mock_redis.pipeline.return_value = mock_pipe

    # Test
    await CoingeckoPriceCache.set(responses)

    # Assertions
    mock_redis.pipeline.assert_called_once()

    # Verify setex was called with correct keys and values
    assert mock_pipe.setex.call_count == 2
    setex_calls = mock_pipe.setex.call_args_list

    # Check ETH token cache
    eth_call = setex_calls[0]
    assert eth_call[0][0] == "coingecko:price:eth:0xa4b1:0x123:usd"  # key
    assert eth_call[0][1] == CoingeckoPriceCache.DEFAULT_TTL  # ttl
    eth_data = json.loads(eth_call[0][2])  # value
    assert eth_data["price"] == 2000.0
    assert eth_data["coin"] == Chain.ARBITRUM.coin
    assert "cache_status" not in eth_data  # cache_status should be excluded

    # Check BTC token cache
    btc_call = setex_calls[1]
    assert btc_call[0][0] == "coingecko:price:btc:bitcoin_mainnet:usd"  # key
    assert btc_call[0][1] == CoingeckoPriceCache.DEFAULT_TTL  # ttl
    btc_data = json.loads(btc_call[0][2])  # value
    assert btc_data["price"] == 50000.0
    assert btc_data["coin"] == Chain.BITCOIN.coin
    assert "cache_status" not in btc_data  # cache_status should be excluded

    # Verify pipeline was closed
    mock_pipe.aclose.assert_called_once()
    mock_pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_coingecko_set_empty_responses(mock_redis):
    await CoingeckoPriceCache.set([])
    mock_redis.pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_coingecko_set_with_custom_ttl(mock_redis):
    custom_ttl = 120
    response = TokenPriceResponse(
        coin=Chain.ARBITRUM.coin,
        chain_id=Chain.ARBITRUM.chain_id,
        address="0x123",
        price=2000.0,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.COINGECKO,
    )

    # Mock pipeline
    mock_pipe = AsyncMock()
    mock_redis.pipeline.return_value = mock_pipe

    await CoingeckoPriceCache.set([response], ttl=custom_ttl)

    # Verify setex was called with correct ttl
    setex_call = mock_pipe.setex.call_args[0]
    assert setex_call[1] == custom_ttl  # ttl

    # Verify pipeline was closed
    mock_pipe.aclose.assert_called_once()
    mock_pipe.execute.assert_called_once()


# JupiterPriceCache Tests
@pytest.mark.asyncio
async def test_jupiter_get_empty_batch(mock_redis):
    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    cached_responses, batch_to_fetch = await JupiterPriceCache.get(batch)

    assert len(cached_responses) == 0
    assert batch_to_fetch.is_empty()
    mock_redis.mget.assert_not_called()


@pytest.mark.asyncio
async def test_jupiter_get_with_cached_values(mock_redis):
    # Setup test data - Jupiter cache only works with tokens that have addresses
    usdc_request = TokenPriceRequest(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC on Solana
        vs_currency=VsCurrency.USD,
    )
    usdt_request = TokenPriceRequest(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT on Solana
        vs_currency=VsCurrency.USD,
    )

    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    batch.add(usdc_request)
    batch.add(usdt_request)

    # Mock cached values
    usdc_response = TokenPriceResponse(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        price=1.01,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.JUPITER,
    )
    usdt_response = TokenPriceResponse(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        price=1.02,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.JUPITER,
    )

    # Create cached data without cache_status
    usdc_data = usdc_response.model_dump(exclude={"cache_status"})
    usdt_data = usdt_response.model_dump(exclude={"cache_status"})

    mock_redis.mget.return_value = [
        json.dumps(usdc_data),
        json.dumps(usdt_data),
    ]

    # Test
    cached_responses, batch_to_fetch = await JupiterPriceCache.get(batch)

    # Assertions
    assert len(cached_responses) == 2
    assert batch_to_fetch.size() == 0
    assert all(
        response.cache_status == CacheStatus.HIT for response in cached_responses
    )
    assert cached_responses[0].price == 1.01
    assert cached_responses[1].price == 1.02

    # Verify cache keys were generated correctly
    mock_redis.mget.assert_called_once()
    called_keys = mock_redis.mget.call_args[0][0]
    assert len(called_keys) == 2
    assert (
        called_keys[0]
        == "jupiter:price:epjfwdd5aufqssqem2qn1xzybapc8g4weggkzwytdt1v:usd"
    )
    assert (
        called_keys[1]
        == "jupiter:price:es9vmfrzacermjfrf4h2fyd4kconky11mcce8benwnyb:usd"
    )


@pytest.mark.asyncio
async def test_jupiter_get_with_mixed_cache_status(mock_redis):
    # Setup test data
    usdc_request = TokenPriceRequest(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        vs_currency=VsCurrency.USD,
    )
    usdt_request = TokenPriceRequest(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        vs_currency=VsCurrency.USD,
    )

    batch = BatchTokenPriceRequests.from_vs_currency(VsCurrency.USD)
    batch.add(usdc_request)
    batch.add(usdt_request)

    # Mock cached values (only USDC is cached)
    usdc_response = TokenPriceResponse(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        price=1.01,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.JUPITER,
    )

    # Create cached data without cache_status
    usdc_data = usdc_response.model_dump(exclude={"cache_status"})

    mock_redis.mget.return_value = [json.dumps(usdc_data), None]

    # Test
    cached_responses, batch_to_fetch = await JupiterPriceCache.get(batch)

    # Assertions
    assert len(cached_responses) == 1
    assert batch_to_fetch.size() == 1
    assert cached_responses[0].coin == Chain.SOLANA.coin
    assert cached_responses[0].cache_status == CacheStatus.HIT
    assert batch_to_fetch.requests[0].coin == Chain.SOLANA.coin
    assert (
        batch_to_fetch.requests[0].address
        == "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    )

    # Verify cache keys were generated correctly
    mock_redis.mget.assert_called_once()
    called_keys = mock_redis.mget.call_args[0][0]
    assert len(called_keys) == 2
    assert (
        called_keys[0]
        == "jupiter:price:epjfwdd5aufqssqem2qn1xzybapc8g4weggkzwytdt1v:usd"
    )
    assert (
        called_keys[1]
        == "jupiter:price:es9vmfrzacermjfrf4h2fyd4kconky11mcce8benwnyb:usd"
    )


@pytest.mark.asyncio
async def test_jupiter_set_multiple_responses(mock_redis):
    # Setup test data
    responses = [
        TokenPriceResponse(
            coin=Chain.SOLANA.coin,
            chain_id=Chain.SOLANA.chain_id,
            address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            price=1.01,
            vs_currency=VsCurrency.USD,
            cache_status=CacheStatus.HIT,
            source=PriceSource.JUPITER,
        ),
        TokenPriceResponse(
            coin=Chain.SOLANA.coin,
            chain_id=Chain.SOLANA.chain_id,
            address="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            price=1.02,
            vs_currency=VsCurrency.USD,
            cache_status=CacheStatus.HIT,
            source=PriceSource.JUPITER,
        ),
    ]

    # Mock pipeline
    mock_pipe = AsyncMock()
    mock_redis.pipeline.return_value = mock_pipe

    # Test
    await JupiterPriceCache.set(responses)

    # Assertions
    mock_redis.pipeline.assert_called_once()

    # Verify setex was called with correct keys and values
    assert mock_pipe.setex.call_count == 2
    setex_calls = mock_pipe.setex.call_args_list

    # Check USDC token cache
    usdc_call = setex_calls[0]
    assert (
        usdc_call[0][0]
        == "jupiter:price:epjfwdd5aufqssqem2qn1xzybapc8g4weggkzwytdt1v:usd"
    )  # key
    assert usdc_call[0][1] == JupiterPriceCache.DEFAULT_TTL  # ttl
    usdc_data = json.loads(usdc_call[0][2])  # value
    assert usdc_data["price"] == 1.01
    assert usdc_data["coin"] == Chain.SOLANA.coin
    assert "cache_status" not in usdc_data  # cache_status should be excluded

    # Check USDT token cache
    usdt_call = setex_calls[1]
    assert (
        usdt_call[0][0]
        == "jupiter:price:es9vmfrzacermjfrf4h2fyd4kconky11mcce8benwnyb:usd"
    )  # key
    assert usdt_call[0][1] == JupiterPriceCache.DEFAULT_TTL  # ttl
    usdt_data = json.loads(usdt_call[0][2])  # value
    assert usdt_data["price"] == 1.02
    assert usdt_data["coin"] == Chain.SOLANA.coin
    assert "cache_status" not in usdt_data  # cache_status should be excluded

    # Verify pipeline was closed
    mock_pipe.aclose.assert_called_once()
    mock_pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_jupiter_set_empty_responses(mock_redis):
    await JupiterPriceCache.set([])
    mock_redis.pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_jupiter_set_with_custom_ttl(mock_redis):
    custom_ttl = 600  # 10 minutes
    response = TokenPriceResponse(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        price=1.01,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.JUPITER,
    )

    # Mock pipeline
    mock_pipe = AsyncMock()
    mock_redis.pipeline.return_value = mock_pipe

    await JupiterPriceCache.set([response], ttl=custom_ttl)

    # Verify setex was called with correct ttl
    setex_call = mock_pipe.setex.call_args[0]
    assert setex_call[1] == custom_ttl  # ttl

    # Verify pipeline was closed
    mock_pipe.aclose.assert_called_once()
    mock_pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_jupiter_cache_key_generation():
    """Test that Jupiter cache keys are generated correctly with lowercase addresses"""
    request = TokenPriceRequest(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        vs_currency=VsCurrency.USD,
    )

    cache_key = JupiterPriceCache._get_cache_key(request, VsCurrency.USD)
    expected_key = "jupiter:price:epjfwdd5aufqssqem2qn1xzybapc8g4weggkzwytdt1v:usd"
    assert cache_key == expected_key

    # Test with response object
    response = TokenPriceResponse(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        price=1.02,
        vs_currency=VsCurrency.USD,
        cache_status=CacheStatus.HIT,
        source=PriceSource.JUPITER,
    )

    cache_key = JupiterPriceCache._get_cache_key(response, VsCurrency.USD)
    expected_key = "jupiter:price:es9vmfrzacermjfrf4h2fyd4kconky11mcce8benwnyb:usd"
    assert cache_key == expected_key


@pytest.mark.asyncio
async def test_jupiter_default_ttl():
    """Test that Jupiter cache uses the correct default TTL"""
    assert JupiterPriceCache.DEFAULT_TTL == 300  # 5 minutes
