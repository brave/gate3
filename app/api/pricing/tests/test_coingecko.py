from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.api.common.models import Chain, Coin
from app.api.pricing.coingecko import CoinGeckoClient
from app.api.pricing.models import (
    BatchTokenPriceRequests,
    CoingeckoPlatform,
    TokenPriceRequest,
    VsCurrency,
)


@pytest.fixture
def client():
    return CoinGeckoClient()


@pytest.fixture
def mock_httpx_client():
    with patch("app.api.pricing.coingecko.create_http_client") as mock:
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


@pytest.mark.asyncio
async def test_filter_excludes_native_token_with_null_native_token_id(client):
    """Test that filter marks tokens as unavailable when platform has null native_token_id."""
    batch = BatchTokenPriceRequests(
        requests=[
            TokenPriceRequest(coin=Coin.ETH, chain_id="0xad", address=None),
        ],
        vs_currency=VsCurrency.USD,
    )

    with (
        patch.object(client, "get_platform_map") as mock_platform_map,
        patch.object(client, "get_coin_map") as mock_coin_map,
    ):
        mock_platform_map.return_value = {
            "some-platform": CoingeckoPlatform(
                id="some-platform",
                chain_id="0xad",
                native_token_id=None,
            )
        }
        mock_coin_map.return_value = {}

        available, unavailable = await client.filter(batch)

        assert available.is_empty()
        assert unavailable.size() == 1


@pytest.mark.asyncio
async def test_native_polkadot_resolves_to_coingecko_id(client):
    """Native DOT (polkadot_mainnet) maps to the 'polkadot' CoinGecko id."""
    request = TokenPriceRequest(
        coin=Chain.POLKADOT.coin, chain_id=Chain.POLKADOT.chain_id, address=None
    )

    coingecko_id = await client._get_coingecko_id_from_request(
        request, platform_map={}, coin_map={}
    )

    assert coingecko_id == "polkadot"


@pytest.mark.asyncio
async def test_filter_includes_native_polkadot(client):
    """Native DOT is available on CoinGecko without needing platform/coin maps."""
    batch = BatchTokenPriceRequests(
        requests=[
            TokenPriceRequest(
                coin=Chain.POLKADOT.coin,
                chain_id=Chain.POLKADOT.chain_id,
                address=None,
            ),
        ],
        vs_currency=VsCurrency.USD,
    )

    with (
        patch.object(client, "get_platform_map") as mock_platform_map,
        patch.object(client, "get_coin_map") as mock_coin_map,
    ):
        mock_platform_map.return_value = {}
        mock_coin_map.return_value = {}

        available, unavailable = await client.filter(batch)

        assert available.size() == 1
        assert unavailable.is_empty()


@pytest.mark.asyncio
async def test_filter_includes_native_polkadot_asset_hub(client):
    """Native DOT on Polkadot Asset Hub is available on CoinGecko without platform/coin maps."""
    batch = BatchTokenPriceRequests(
        requests=[
            TokenPriceRequest(
                coin=Chain.POLKADOT_ASSET_HUB.coin,
                chain_id=Chain.POLKADOT_ASSET_HUB.chain_id,
                address=None,
            ),
        ],
        vs_currency=VsCurrency.USD,
    )

    with (
        patch.object(client, "get_platform_map") as mock_platform_map,
        patch.object(client, "get_coin_map") as mock_coin_map,
    ):
        mock_platform_map.return_value = {}
        mock_coin_map.return_value = {}

        available, unavailable = await client.filter(batch)

        assert available.size() == 1
        assert unavailable.is_empty()


@pytest.mark.asyncio
async def test_get_prices_native_polkadot_asset_hub(client, mock_httpx_client):
    """Native DOT on Polkadot Asset Hub is priced via the 'polkadot' CoinGecko id."""
    batch = BatchTokenPriceRequests(
        requests=[
            TokenPriceRequest(
                coin=Chain.POLKADOT_ASSET_HUB.coin,
                chain_id=Chain.POLKADOT_ASSET_HUB.chain_id,
                address=None,
            ),
        ],
        vs_currency=VsCurrency.USD,
    )

    with (
        patch("app.api.pricing.coingecko.CoingeckoPriceCache.get") as mock_cache,
        patch(
            "app.api.pricing.coingecko.CoingeckoPriceCache.set", new_callable=AsyncMock
        ),
        patch.object(client, "get_platform_map") as mock_platform_map,
        patch.object(client, "get_coin_map") as mock_coin_map,
    ):
        mock_cache.return_value = ([], batch)
        mock_platform_map.return_value = {}
        mock_coin_map.return_value = {}

        mock_response = AsyncMock()
        mock_response.json = lambda: {"polkadot": {"usd": 4.2, "usd_24h_change": 1.5}}
        mock_response.raise_for_status = lambda: None
        mock_httpx_client.get.return_value = mock_response

        results = await client.get_prices(batch)

    assert len(results) == 1
    assert results[0].price == 4.2
    assert results[0].coin == Chain.POLKADOT_ASSET_HUB.coin
    assert results[0].chain_id == Chain.POLKADOT_ASSET_HUB.chain_id
    assert results[0].source == "coingecko"


@pytest.mark.asyncio
async def test_get_platform_map_maps_polkadot_to_asset_hub(client, mock_httpx_client):
    """CoinGecko's 'polkadot' platform is mapped to our Asset Hub chain."""
    mock_response = AsyncMock()
    mock_response.json = lambda: [
        {"id": "polkadot", "chain_identifier": None, "native_coin_id": "polkadot"},
        {"id": "ethereum", "chain_identifier": 1, "native_coin_id": "ethereum"},
    ]
    mock_response.raise_for_status = lambda: None
    mock_httpx_client.get.return_value = mock_response

    with (
        patch(
            "app.api.pricing.coingecko.PlatformMapCache.get",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.api.pricing.coingecko.PlatformMapCache.set", new_callable=AsyncMock),
    ):
        platform_map = await client.get_platform_map()

    assert platform_map["polkadot"].chain_id == Chain.POLKADOT_ASSET_HUB.chain_id
    assert platform_map["polkadot"].native_token_id == "polkadot"


@pytest.mark.asyncio
async def test_get_coin_map_maps_asset_hub_assets_and_skips_empty(
    client, mock_httpx_client
):
    """Asset Hub keeps numeric asset IDs only; empty and mistagged EVM addresses are skipped."""
    platform_map = {
        "polkadot": CoingeckoPlatform(
            id="polkadot",
            chain_id=Chain.POLKADOT_ASSET_HUB.chain_id,
            native_token_id="polkadot",
        ),
    }
    evm_address = "0xef3a930e1ffffacd2fc13434ac81bd278b0ecc8d"
    mock_response = AsyncMock()
    mock_response.json = lambda: [
        {"id": "usd-coin", "symbol": "usdc", "platforms": {"polkadot": "1337"}},
        {"id": "acala", "symbol": "aca", "platforms": {"polkadot": ""}},
        # CoinGecko occasionally mistags an EVM address under the polkadot platform.
        {"id": "stafi", "symbol": "fis", "platforms": {"polkadot": evm_address}},
    ]
    mock_response.raise_for_status = lambda: None
    mock_httpx_client.get.return_value = mock_response

    with (
        patch(
            "app.api.pricing.coingecko.CoinMapCache.get",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.api.pricing.coingecko.CoinMapCache.set", new_callable=AsyncMock),
    ):
        coin_map = await client.get_coin_map(platform_map)

    asset_hub = Chain.POLKADOT_ASSET_HUB.chain_id
    assert coin_map[asset_hub] == {"1337": "usd-coin"}
    assert "" not in coin_map[asset_hub]
    assert evm_address not in coin_map[asset_hub]


@pytest.mark.asyncio
async def test_get_coin_map_skips_platforms_without_chain_id(client, mock_httpx_client):
    """Platforms with no resolved chain_id must not create a null key in the coin map."""
    platform_map = {
        "ethereum": CoingeckoPlatform(
            id="ethereum", chain_id="0x1", native_token_id="ethereum"
        ),
        "near-protocol": CoingeckoPlatform(
            id="near-protocol", chain_id=None, native_token_id="near"
        ),
    }
    mock_response = AsyncMock()
    mock_response.json = lambda: [
        {
            "id": "usd-coin",
            "symbol": "usdc",
            "platforms": {"ethereum": "0xA0b8", "near-protocol": "usdc.near"},
        },
    ]
    mock_response.raise_for_status = lambda: None
    mock_httpx_client.get.return_value = mock_response

    with (
        patch(
            "app.api.pricing.coingecko.CoinMapCache.get",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.api.pricing.coingecko.CoinMapCache.set", new_callable=AsyncMock),
    ):
        coin_map = await client.get_coin_map(platform_map)

    assert None not in coin_map
    assert coin_map["0x1"] == {"0xa0b8": "usd-coin"}


@pytest.mark.asyncio
async def test_filter_token_lookup_is_case_insensitive_on_chain_id(client):
    """A mixed-case chain_id still resolves against the lowercase-keyed coin map."""
    batch = BatchTokenPriceRequests(
        requests=[
            TokenPriceRequest(coin=Coin.ETH, chain_id="0X1", address="0xABC"),
        ],
        vs_currency=VsCurrency.USD,
    )

    with (
        patch.object(client, "get_platform_map") as mock_platform_map,
        patch.object(client, "get_coin_map") as mock_coin_map,
    ):
        mock_platform_map.return_value = {}
        mock_coin_map.return_value = {"0x1": {"0xabc": "some-token"}}

        available, unavailable = await client.filter(batch)

        assert available.size() == 1
        assert unavailable.is_empty()


@pytest.mark.asyncio
async def test_filter_excludes_relay_chain_polkadot_token(client):
    """Relay-chain Polkadot supports only native DOT; a token address is unavailable."""
    batch = BatchTokenPriceRequests(
        requests=[
            TokenPriceRequest(
                coin=Chain.POLKADOT.coin,
                chain_id=Chain.POLKADOT.chain_id,
                address="1337",
            ),
        ],
        vs_currency=VsCurrency.USD,
    )

    with (
        patch.object(client, "get_platform_map") as mock_platform_map,
        patch.object(client, "get_coin_map") as mock_coin_map,
    ):
        mock_platform_map.return_value = {}
        # Even if a coin map existed for the relay chain, it must not be consulted.
        mock_coin_map.return_value = {Chain.POLKADOT.chain_id: {"1337": "usd-coin"}}

        available, unavailable = await client.filter(batch)

        assert available.is_empty()
        assert unavailable.size() == 1


@pytest.mark.asyncio
async def test_get_prices_polkadot_asset_hub_token(client, mock_httpx_client):
    """A non-native Asset Hub asset (USDC, id 1337) is priced via its CoinGecko id."""
    asset_hub = Chain.POLKADOT_ASSET_HUB.chain_id
    batch = BatchTokenPriceRequests(
        requests=[
            TokenPriceRequest(coin=Coin.DOT, chain_id=asset_hub, address="1337"),
        ],
        vs_currency=VsCurrency.USD,
    )

    with (
        patch("app.api.pricing.coingecko.CoingeckoPriceCache.get") as mock_cache,
        patch(
            "app.api.pricing.coingecko.CoingeckoPriceCache.set", new_callable=AsyncMock
        ),
        patch.object(client, "get_platform_map") as mock_platform_map,
        patch.object(client, "get_coin_map") as mock_coin_map,
    ):
        mock_cache.return_value = ([], batch)
        mock_platform_map.return_value = {}
        mock_coin_map.return_value = {asset_hub: {"1337": "usd-coin"}}

        mock_response = AsyncMock()
        mock_response.json = lambda: {"usd-coin": {"usd": 1.0, "usd_24h_change": 0.1}}
        mock_response.raise_for_status = lambda: None
        mock_httpx_client.get.return_value = mock_response

        results = await client.get_prices(batch)

    assert len(results) == 1
    assert results[0].price == 1.0
    assert results[0].address == "1337"
    assert results[0].chain_id == asset_hub
    assert results[0].source == "coingecko"


@pytest.mark.asyncio
async def test_filter_includes_native_token_when_native_token_id_present(client):
    """Test that filter marks tokens as available when platform has native_token_id."""
    batch = BatchTokenPriceRequests(
        requests=[
            TokenPriceRequest(coin=Coin.ETH, chain_id="0x1", address=None),
        ],
        vs_currency=VsCurrency.USD,
    )

    with (
        patch.object(client, "get_platform_map") as mock_platform_map,
        patch.object(client, "get_coin_map") as mock_coin_map,
    ):
        mock_platform_map.return_value = {
            "ethereum": CoingeckoPlatform(
                id="ethereum",
                chain_id="0x1",
                native_token_id="ethereum",
            )
        }
        mock_coin_map.return_value = {}

        available, unavailable = await client.filter(batch)

        assert available.size() == 1
        assert unavailable.is_empty()
