import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import fakeredis
import pytest

from app.api.common.models import Chain
from app.api.tokens.manager import TokenManager
from app.api.tokens.models import TokenInfo, TokenSource


class AsyncFakeRedis(fakeredis.FakeAsyncRedis):
    async def hgetall(self, key):
        result = await super().hgetall(key)
        # Convert bytes to strings for compatibility
        if result:
            return {
                k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8")
                if isinstance(v, bytes)
                else v
                for k, v in result.items()
            }
        return result

    def ft(self, index_name):
        return AsyncMock()


@dataclass
class MockSearchResult:
    docs: list
    total: int


class MockSearchDoc:
    def __init__(self, doc_id, **kwargs):
        self.id = doc_id
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def cache():
    redis_client = AsyncFakeRedis(server=fakeredis.FakeServer())

    with patch("app.api.tokens.manager.Cache") as mock_cache:
        mock_cache.get_client.return_value.__aenter__.return_value = redis_client
        mock_cache.get_client.return_value.__aexit__.return_value = None
        yield mock_cache


@pytest.fixture
def sample_token_info():
    return TokenInfo(
        coin=Chain.ETHEREUM.coin,
        chain_id=Chain.ETHEREUM.chain_id,
        address="0x1234567890123456789012345678901234567890",
        name="Test Token",
        symbol="TEST",
        decimals=18,
        logo="https://example.com/logo.png",
        sources=[TokenSource.COINGECKO],
    )


@pytest.mark.asyncio
async def test_add_and_get_token(cache, sample_token_info):
    # Add the token
    await TokenManager.add(sample_token_info)

    # Get the token
    result = await TokenManager.get(
        Chain.ETHEREUM.coin,
        Chain.ETHEREUM.chain_id,
        "0x1234567890123456789012345678901234567890",
    )

    # Verify the token was retrieved correctly
    assert result is not None
    assert result.name == "Test Token"
    assert result.symbol == "TEST"
    assert result.decimals == 18
    assert result.address == "0x1234567890123456789012345678901234567890"
    assert result.sources == [TokenSource.COINGECKO]


@pytest.mark.asyncio
async def test_get_token_not_found(cache):
    # Try to get a non-existent token
    result = await TokenManager.get(
        Chain.ETHEREUM.coin,
        Chain.ETHEREUM.chain_id,
        "0x0000000000000000000000000000000000000000",
    )

    # Verify no token was found
    assert result is None


@pytest.mark.asyncio
async def test_add_bitcoin(cache):
    token_info = TokenInfo(
        coin=Chain.BITCOIN.coin,
        chain_id=Chain.BITCOIN.chain_id,
        address=None,
        name="Bitcoin",
        symbol="BTC",
        decimals=8,
        logo="https://example.com/btc.png",
        sources=[TokenSource.COINGECKO],
    )

    # Add the token
    await TokenManager.add(token_info)

    # Get the token
    result = await TokenManager.get(Chain.BITCOIN.coin, Chain.BITCOIN.chain_id, None)

    # Verify the token was retrieved correctly
    assert result is not None
    assert result.name == "Bitcoin"
    assert result.symbol == "BTC"
    assert result.decimals == 8
    assert result.address is None
    assert result.chain_id == Chain.BITCOIN.chain_id
    assert result.logo == "https://example.com/btc.png"
    assert result.sources == [TokenSource.COINGECKO]


@pytest.mark.asyncio
async def test_search_functionality(cache, sample_token_info):
    # Add the token first
    await TokenManager.add(sample_token_info)

    # Get the redis client from the cache fixture
    redis_client = cache.get_client.return_value.__aenter__.return_value

    # Mock the ft.search functionality since fakeredis doesn't support it
    mock_index = AsyncMock()

    # Create mock search result
    mock_doc = MockSearchDoc(
        doc_id="token:eth:0x1:0x1234567890123456789012345678901234567890",
        coin="eth",
        chain_id="0x1",
        address="0x1234567890123456789012345678901234567890",
        name="Test Token",
        symbol="TEST",
        decimals="18",
        logo="https://example.com/logo.png",
        sources=json.dumps([TokenSource.COINGECKO.value]),
    )

    mock_result = MockSearchResult(docs=[mock_doc], total=1)
    mock_index.search = AsyncMock(return_value=mock_result)

    # Mock the ft method to return our mock index
    redis_client.ft = MagicMock(return_value=mock_index)

    # Mock create_index to return the mock index
    with patch.object(TokenManager, "create_index", return_value=mock_index):
        # Search by symbol
        result = await TokenManager.search("TEST", 0, 10)

        # Verify the search found the token
        assert len(result.results) == 1
        assert result.results[0].symbol == "TEST"
        assert result.results[0].name == "Test Token"
        assert result.total == 1


@pytest.mark.asyncio
async def test_search_no_results(cache):
    # Get the redis client from the cache fixture
    redis_client = cache.get_client.return_value.__aenter__.return_value

    # Mock the ft.search functionality
    mock_index = AsyncMock()

    # Create empty mock search result
    mock_result = MockSearchResult(docs=[], total=0)
    mock_index.search = AsyncMock(return_value=mock_result)

    # Mock the ft method to return our mock index
    redis_client.ft = MagicMock(return_value=mock_index)

    # Mock create_index to return the mock index
    with patch.object(TokenManager, "create_index", return_value=mock_index):
        # Search for non-existent token
        result = await TokenManager.search("NONEXISTENT", 0, 10)

        # Verify no results
        assert len(result.results) == 0
        assert result.total == 0


@pytest.mark.asyncio
async def test_refresh_with_coingecko_data(cache):
    # Mock the Coingecko API response
    mock_response = Mock()
    mock_response.json.return_value = {
        "0x1": {
            "0x1234567890123456789012345678901234567890": {
                "name": "Test Token",
                "symbol": "TEST",
                "decimals": 18,
                "logo": "https://example.com/logo.png",
            }
        }
    }

    with (
        patch.object(TokenManager, "create_index"),
        patch("app.api.tokens.manager.requests.get", return_value=mock_response),
        patch.object(TokenManager, "ingest_from_jupiter"),
    ):
        # Refresh tokens (which includes Coingecko ingestion)
        await TokenManager.refresh()

        # Verify the token was stored and can be retrieved
        result = await TokenManager.get(
            Chain.ETHEREUM.coin,
            Chain.ETHEREUM.chain_id,
            "0x1234567890123456789012345678901234567890",
        )

        # Verify the token was retrieved correctly
        assert result is not None
        assert result.name == "Test Token"
        assert result.symbol == "TEST"
        assert result.decimals == 18
        assert TokenSource.COINGECKO in result.sources


@pytest.mark.asyncio
async def test_refresh_with_jupiter_data(cache):
    # Mock the Jupiter API response
    mock_response = Mock()
    mock_response.json.return_value = [
        {
            "id": "So11111111111111111111111111111111111111112",
            "name": "Wrapped SOL",
            "symbol": "SOL",
            "decimals": 9,
            "icon": "https://example.com/sol.png",
        }
    ]

    with (
        patch.object(TokenManager, "create_index"),
        patch("app.api.tokens.manager.requests.get", return_value=mock_response),
        patch.object(TokenManager, "ingest_from_coingecko"),
    ):
        # Refresh tokens (which includes Jupiter ingestion)
        await TokenManager.refresh()

        # Verify the token was stored and can be retrieved
        result = await TokenManager.get(
            Chain.SOLANA.coin,
            Chain.SOLANA.chain_id,
            "So11111111111111111111111111111111111111112",
        )

        # Verify the token was retrieved correctly
        assert result is not None
        assert result.name == "Wrapped SOL"
        assert result.symbol == "SOL"
        assert result.decimals == 9
        assert TokenSource.JUPITER_VERIFIED in result.sources


@pytest.mark.asyncio
async def test_multiple_tokens(cache):
    # Create multiple tokens
    tokens = [
        TokenInfo(
            coin=Chain.ETHEREUM.coin,
            chain_id=Chain.ETHEREUM.chain_id,
            address=f"0x{i:040x}",
            name=f"Token {i}",
            symbol=f"TKN{i}",
            decimals=18,
            logo=f"https://example.com/token{i}.png",
            sources=[TokenSource.COINGECKO],
        )
        for i in range(1, 4)  # 3 tokens
    ]

    # Add all tokens
    for token in tokens:
        await TokenManager.add(token)

    # Verify all tokens can be retrieved
    for i, token in enumerate(tokens, 1):
        result = await TokenManager.get(
            Chain.ETHEREUM.coin, Chain.ETHEREUM.chain_id, f"0x{i:040x}"
        )
        assert result is not None
        assert result.name == f"Token {i}"
        assert result.symbol == f"TKN{i}"
        assert result.address == f"0x{i:040x}"


QUERIES = [
    # Single word queries
    (
        "bitcoin",
        "(@symbol_lower:(bitcoin)) => { $weight: 5.0; } | "
        "(@address_lower:(bitcoin)) => { $weight: 5.0; } | "
        "(@name_lower:(bitcoin)) => { $weight: 2.0; } | "
        "(@name_lower:(*bitcoin*)) => { $weight: 1.0; } | "
        "(@name_lower:(%%bitcoin%%)) => { $weight: 0.5; }",
    ),
    # Two word queries
    (
        "basic attention",
        "(@name_lower:(basic attention)) => { $weight: 2.0; } | "
        "(@name_lower:(*basic* *attention*)) => { $weight: 1.0; } | "
        "(@name_lower:(%%basic%% %%attention%%)) => { $weight: 0.5; }",
    ),
    # Three word queries
    (
        "basic attention token",
        "(@name_lower:(basic attention token)) => { $weight: 2.0; } | "
        "(@name_lower:(*basic* *attention* *token*)) => { $weight: 1.0; } | "
        "(@name_lower:(%%basic%% %%attention%% %%token%%)) => { $weight: 0.5; }",
    ),
    # Four word queries
    (
        "basic attention token portal",
        "(@name_lower:(basic attention token portal)) => { $weight: 2.0; } | "
        "(@name_lower:(*basic* *attention* *token* *portal*)) => { $weight: 1.0; } | "
        "(@name_lower:(%%basic%% %%attention%% %%token%% %%portal%%)) => { $weight: 0.5; }",
    ),
    # Case insensitive test
    (
        "BiTcOiN",
        "(@symbol_lower:(bitcoin)) => { $weight: 5.0; } | "
        "(@address_lower:(bitcoin)) => { $weight: 5.0; } | "
        "(@name_lower:(bitcoin)) => { $weight: 2.0; } | "
        "(@name_lower:(*bitcoin*)) => { $weight: 1.0; } | "
        "(@name_lower:(%%bitcoin%%)) => { $weight: 0.5; }",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,expected_query",
    QUERIES,
    ids=[x[0] for x in QUERIES],
)
async def test_search_query_construction(cache, query, expected_query):
    """Test that queries construct the exact expected Query string."""
    # Hardcoded offset and limit for all tests
    offset, limit = 0, 10

    # Mock the search index and Query class
    mock_index = AsyncMock()
    mock_result = MockSearchResult(docs=[], total=0)
    mock_index.search = AsyncMock(return_value=mock_result)

    with (
        patch.object(TokenManager, "create_index", return_value=mock_index),
        patch("app.api.tokens.manager.Query") as mock_query_class,
    ):
        # Mock Query instance
        mock_query_instance = Mock()
        mock_query_class.return_value = mock_query_instance
        mock_query_instance.dialect.return_value = mock_query_instance
        mock_query_instance.paging.return_value = mock_query_instance

        # Test the query
        await TokenManager.search(query, offset, limit)

        # Verify Query was called with the exact expected search query
        mock_query_class.assert_called_once()
        actual_query = mock_query_class.call_args[0][0]
        assert actual_query == expected_query

        # Verify dialect and paging were called
        mock_query_instance.dialect.assert_called_once_with(2)
        mock_query_instance.paging.assert_called_once_with(offset, limit)
