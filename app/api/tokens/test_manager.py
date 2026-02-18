import json
import logging
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import fakeredis
import httpx
import pytest
import respx

from app.api.common.models import Chain, Coin, TokenInfo, TokenSource, TokenType
from app.api.tokens.contants import SPL_TOKEN_2022_PROGRAM_ID, SPL_TOKEN_PROGRAM_ID
from app.api.tokens.manager import TokenManager


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

    def pipeline(self):
        return MockPipeline(self)

    def ft(self, index_name):
        return AsyncMock()


class MockPipeline:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.commands = []

    def hgetall(self, key):
        self.commands.append(("hgetall", key))
        return self

    def hset(self, key, mapping=None):
        self.commands.append(("hset", key, mapping))
        return self

    async def execute(self):
        results = []
        for command in self.commands:
            if command[0] == "hgetall":
                result = await self.redis_client.hgetall(command[1])
                results.append(result)
            elif command[0] == "hset":
                # Actually store the data in the mock Redis client
                await self.redis_client.hset(command[1], mapping=command[2])
                results.append(None)
        return results


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
        token_type=TokenType.ERC20,
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
        token_type=TokenType.UNKNOWN,
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
        token_type=TokenType.ERC20.value,
        near_intents_asset_id=None,
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
async def test_list_tokens_functionality(cache, sample_token_info):
    # Add the token first
    await TokenManager.add(sample_token_info)

    # List tokens for Ethereum
    result = await TokenManager.list_tokens(
        Chain.ETHEREUM.coin, Chain.ETHEREUM.chain_id
    )

    # Verify the list found the token
    assert len(result) == 1
    assert result[0].symbol == "TEST"
    assert result[0].name == "Test Token"
    assert result[0].coin == Chain.ETHEREUM.coin
    assert result[0].chain_id == Chain.ETHEREUM.chain_id

    # List tokens for non-existent chain
    result = await TokenManager.list_tokens(Chain.ETHEREUM.coin, "0x999")
    assert len(result) == 0


@pytest.mark.asyncio
async def test_list_tokens_without_chain_id(cache, sample_token_info):
    # Add the token first
    await TokenManager.add(sample_token_info)

    # Create another token for a different chain to test cross-chain listing
    solana_token = TokenInfo(
        coin=Chain.SOLANA.coin,
        chain_id=Chain.SOLANA.chain_id,
        address="So11111111111111111111111111111111111111112",
        name="Wrapped SOL",
        symbol="WSOL",
        decimals=9,
        logo="https://example.com/wsol-logo.png",
        sources=[TokenSource.JUPITER_VERIFIED],
        token_type=TokenType.SPL_TOKEN,
    )
    await TokenManager.add(solana_token)

    # List tokens for Ethereum coin only (should return only Ethereum tokens)
    result = await TokenManager.list_tokens(Chain.ETHEREUM.coin, None)

    # Should find only the Ethereum token
    assert len(result) == 1
    assert result[0].symbol == "TEST"
    assert result[0].name == "Test Token"
    assert result[0].coin == Chain.ETHEREUM.coin
    assert result[0].chain_id == Chain.ETHEREUM.chain_id

    # List tokens for Solana coin only (should return only Solana tokens)
    result = await TokenManager.list_tokens(Chain.SOLANA.coin, None)

    # Should find only the Solana token
    assert len(result) == 1
    assert result[0].symbol == "WSOL"
    assert result[0].name == "Wrapped SOL"
    assert result[0].coin == Chain.SOLANA.coin
    assert result[0].chain_id == Chain.SOLANA.chain_id


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
@respx.mock
async def test_refresh_with_coingecko_data(cache):
    # Mock the Coingecko API response
    coingecko_data = {
        "0x1": {
            "0x1234567890123456789012345678901234567890": {
                "name": "Test Token",
                "symbol": "TEST",
                "decimals": 18,
                "logo": "https://example.com/logo.png",
            }
        }
    }
    respx.get(
        "https://raw.githubusercontent.com/brave/token-lists/refs/heads/main/data/v1/coingecko.json"
    ).mock(return_value=httpx.Response(200, json=coingecko_data))

    with (
        patch.object(TokenManager, "create_index"),
        patch.object(TokenManager, "ingest_from_jupiter"),
        patch.object(TokenManager, "ingest_from_near_intents"),
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
@respx.mock
async def test_refresh_with_jupiter_data(cache):
    # Mock the Jupiter API responses
    jupiter_verified_data = [
        {
            "id": "So11111111111111111111111111111111111111112",
            "name": "Wrapped SOL",
            "symbol": "SOL",
            "decimals": 9,
            "icon": "https://example.com/sol.png",
            "tokenProgram": SPL_TOKEN_2022_PROGRAM_ID,
        }
    ]
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=lst").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=verified").mock(
        return_value=httpx.Response(200, json=jupiter_verified_data)
    )

    with (
        patch.object(TokenManager, "create_index"),
        patch.object(TokenManager, "ingest_from_coingecko"),
        patch.object(TokenManager, "ingest_from_near_intents"),
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
        assert result.token_type == TokenType.SPL_TOKEN_2022
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
            token_type=TokenType.ERC20,
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


@pytest.mark.asyncio
async def test_refresh_seeds_all_chains(cache):
    """Verify that every Chain enum member gets a native token seeded."""
    with (
        patch.object(TokenManager, "create_index"),
        patch.object(TokenManager, "ingest_from_coingecko"),
        patch.object(TokenManager, "ingest_from_jupiter"),
        patch.object(TokenManager, "ingest_from_near_intents"),
    ):
        await TokenManager.refresh()

    for chain in Chain:
        result = await TokenManager.get(chain.coin, chain.chain_id, None)
        assert result is not None, f"Native token missing for {chain}"
        assert result.coin == chain.coin
        assert result.chain_id == chain.chain_id
        assert result.address is None
        assert result.name == chain.native_asset_name
        assert result.symbol == chain.symbol
        assert result.decimals == chain.decimals
        assert TokenSource.BRAVE in result.sources


@pytest.mark.asyncio
@respx.mock
async def test_refresh_merges_overlapping_sources(cache):
    """CoinGecko + NEAR Intents provide same token → fields merged correctly."""
    respx.get(
        "https://raw.githubusercontent.com/brave/token-lists/refs/heads/main/data/v1/coingecko.json"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "0x1": {
                    "0xABC": {
                        "name": "TestToken",
                        "symbol": "TT",
                        "decimals": 18,
                        "logo": "https://example.com/logo.png",
                    }
                }
            },
        )
    )
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=lst").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=verified").mock(
        return_value=httpx.Response(200, json=[])
    )

    near_token = TokenInfo(
        coin=Coin.ETH,
        chain_id="0x1",
        address="0xABC",
        name="TestToken",
        symbol="TT",
        decimals=18,
        logo=None,
        sources=[TokenSource.NEAR_INTENTS],
        token_type=TokenType.ERC20,
        near_intents_asset_id="near:asset:1",
    )

    with (
        patch.object(TokenManager, "create_index"),
        patch(
            "app.api.swap.providers.near_intents.client.NearIntentsClient"
        ) as MockNearClient,
    ):
        MockNearClient.return_value.get_supported_tokens = AsyncMock(
            return_value=[near_token]
        )
        await TokenManager.refresh()

    result = await TokenManager.get(Coin.ETH, "0x1", "0xABC")
    assert result is not None
    # Sources accumulated from both providers
    assert TokenSource.COINGECKO in result.sources
    assert TokenSource.NEAR_INTENTS in result.sources
    # CoinGecko logo preserved (NEAR Intents had None)
    assert result.logo == "https://example.com/logo.png"
    # NEAR Intents asset_id preserved (CoinGecko didn't have one)
    assert result.near_intents_asset_id == "near:asset:1"


@pytest.mark.asyncio
@respx.mock
async def test_refresh_continues_when_coingecko_fails(cache):
    """CoinGecko returns HTTP 500, Jupiter succeeds → native + Jupiter tokens still exist."""
    respx.get(
        "https://raw.githubusercontent.com/brave/token-lists/refs/heads/main/data/v1/coingecko.json"
    ).mock(return_value=httpx.Response(500))

    jupiter_data = [
        {
            "id": "So11111111111111111111111111111111111111112",
            "name": "Wrapped SOL",
            "symbol": "SOL",
            "decimals": 9,
            "icon": "https://example.com/sol.png",
            "tokenProgram": SPL_TOKEN_2022_PROGRAM_ID,
        }
    ]
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=lst").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=verified").mock(
        return_value=httpx.Response(200, json=jupiter_data)
    )

    with (
        patch.object(TokenManager, "create_index"),
        patch.object(TokenManager, "ingest_from_near_intents"),
    ):
        await TokenManager.refresh()

    # Native tokens still present
    for chain in Chain:
        result = await TokenManager.get(chain.coin, chain.chain_id, None)
        assert result is not None, f"Native token missing for {chain}"

    # Jupiter token still present
    result = await TokenManager.get(
        Chain.SOLANA.coin,
        Chain.SOLANA.chain_id,
        "So11111111111111111111111111111111111111112",
    )
    assert result is not None
    assert result.name == "Wrapped SOL"


@pytest.mark.asyncio
async def test_refresh_logs_error_on_source_failure(cache, caplog):
    """Source fails → error logged with source name."""
    with (
        patch.object(TokenManager, "create_index"),
        patch.object(
            TokenManager, "ingest_from_coingecko", side_effect=RuntimeError("timeout")
        ),
        patch.object(TokenManager, "ingest_from_jupiter"),
        patch.object(TokenManager, "ingest_from_near_intents"),
        caplog.at_level(logging.ERROR, logger="app.api.tokens.manager"),
    ):
        await TokenManager.refresh()

    assert "Failed to ingest tokens from coingecko" in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_refresh_prefers_png_logo_over_svg(cache):
    """CoinGecko provides PNG logo, Jupiter provides SVG → PNG is kept."""
    sol_address = "So11111111111111111111111111111111111111112"
    png_logo = "https://assets.coingecko.com/coins/images/sol.png"
    svg_logo = "https://raw.githubusercontent.com/jup-ag/sol.svg"

    respx.get(
        "https://raw.githubusercontent.com/brave/token-lists/refs/heads/main/data/v1/coingecko.json"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                Chain.SOLANA.chain_id: {
                    sol_address: {
                        "name": "Wrapped SOL",
                        "symbol": "SOL",
                        "decimals": 9,
                        "logo": png_logo,
                    }
                }
            },
        )
    )
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=lst").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=verified").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": sol_address,
                    "name": "Wrapped SOL",
                    "symbol": "SOL",
                    "decimals": 9,
                    "icon": svg_logo,
                    "tokenProgram": SPL_TOKEN_PROGRAM_ID,
                }
            ],
        )
    )

    with (
        patch.object(TokenManager, "create_index"),
        patch.object(TokenManager, "ingest_from_near_intents"),
    ):
        await TokenManager.refresh()

    result = await TokenManager.get(
        Chain.SOLANA.coin, Chain.SOLANA.chain_id, sol_address
    )
    assert result is not None
    assert result.logo == png_logo, (
        "PNG logo from CoinGecko should not be replaced by SVG from Jupiter"
    )


@pytest.mark.asyncio
@respx.mock
async def test_refresh_allows_svg_when_no_prior_logo(cache):
    """Jupiter provides SVG logo, no prior logo exists → SVG is used."""
    sol_address = "JupiterOnlyToken111111111111111111111111111"
    svg_logo = "https://raw.githubusercontent.com/jup-ag/token.svg"

    respx.get(
        "https://raw.githubusercontent.com/brave/token-lists/refs/heads/main/data/v1/coingecko.json"
    ).mock(return_value=httpx.Response(200, json={}))
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=lst").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://lite-api.jup.ag/tokens/v2/tag?query=verified").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": sol_address,
                    "name": "Jupiter Only",
                    "symbol": "JONLY",
                    "decimals": 6,
                    "icon": svg_logo,
                    "tokenProgram": SPL_TOKEN_PROGRAM_ID,
                }
            ],
        )
    )

    with (
        patch.object(TokenManager, "create_index"),
        patch.object(TokenManager, "ingest_from_near_intents"),
    ):
        await TokenManager.refresh()

    result = await TokenManager.get(
        Chain.SOLANA.coin, Chain.SOLANA.chain_id, sol_address
    )
    assert result is not None
    assert result.logo == svg_logo, "SVG logo should be used when no prior logo exists"
