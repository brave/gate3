from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.common.models import Chain, Coin
from app.api.swap.models import (
    SwapError,
    SwapErrorKind,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapStatus,
    SwapStatusRequest,
    SwapSupportRequest,
    SwapType,
)
from app.api.tokens.manager import TokenManager

from .client import SquidClient
from .mocks import (
    ETH_ON_ARBITRUM_TOKEN_INFO,
    ETH_ON_ETHEREUM_TOKEN_INFO,
    MOCK_SQUID_ERROR_RESPONSE,
    MOCK_SQUID_ROUTE_RESPONSE,
    MOCK_SQUID_STATUS_ONGOING,
    MOCK_SQUID_STATUS_SUCCESS,
    USDC_ON_ARBITRUM_TOKEN_INFO,
    USDC_ON_ETHEREUM_TOKEN_INFO,
)


@pytest.fixture
def mock_token_manager():
    mock_manager = AsyncMock(spec=TokenManager)
    mock_manager.get = AsyncMock(return_value=None)
    return mock_manager


@pytest.fixture
def client(mock_token_manager):
    with patch("app.api.swap.providers.squid.client.settings") as mock_settings:
        mock_settings.SQUID_INTEGRATOR_ID = "test_integrator_id"
        yield SquidClient(token_manager=mock_token_manager)


@pytest.fixture
def mock_httpx_client():
    with patch("httpx.AsyncClient") as mock:
        mock_client = AsyncMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock.return_value = mock_context
        yield mock_client


@pytest.fixture(autouse=True)
def mock_cache():
    with patch("app.api.swap.cache.Cache.get_client") as mock_get_client:
        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value=None)
        mock_redis_client.setex = AsyncMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_redis_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_client.return_value = mock_context
        yield mock_redis_client


@pytest.mark.asyncio
async def test_get_supported_tokens(client):
    with pytest.raises(NotImplementedError):
        await client.get_supported_tokens()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_coin,source_chain_id,dest_coin,dest_chain_id,expected",
    [
        # Success cases: EVM to EVM cross-chain
        (Coin.ETH, "0x1", Coin.ETH, "0xa4b1", True),  # Ethereum to Arbitrum
        (Coin.ETH, "0xa4b1", Coin.ETH, "0x1", True),  # Arbitrum to Ethereum
        (Coin.ETH, "0x1", Coin.ETH, "0xa", True),  # Ethereum to Optimism
        (Coin.ETH, "0x89", Coin.ETH, "0x2105", True),  # Polygon to Base
        # Same chain (still supported)
        (Coin.ETH, "0x1", Coin.ETH, "0x1", True),  # Ethereum to Ethereum
        # Success cases: EVM to Bitcoin and Solana
        (Coin.ETH, "0x1", Coin.SOL, "0x65", True),  # Ethereum to Solana
        (Coin.ETH, "0xa4b1", Coin.BTC, "bitcoin_mainnet", True),  # Arbitrum to Bitcoin
        # Failure cases
        (Coin.ETH, "0xunknown", Coin.ETH, "0x1", False),  # Unknown EVM chain
        (Coin.BTC, "bitcoin_testnet", Coin.ETH, "0x1", False),  # Bitcoin testnet
        (Coin.SOL, "0x66", Coin.ETH, "0x1", False),  # Unknown Solana chain
        (Coin.ADA, "cardano_mainnet", Coin.ETH, "0x1", False),  # Unsupported coin
        # BTC and SOL as source are not supported
        (Coin.SOL, "0x65", Coin.ETH, "0x1", False),  # Solana to Ethereum
        (Coin.BTC, "bitcoin_mainnet", Coin.ETH, "0x1", False),  # Bitcoin to Ethereum
        (Coin.BTC, "bitcoin_mainnet", Coin.SOL, "0x65", False),  # Bitcoin to Solana
        (Coin.SOL, "0x65", Coin.BTC, "bitcoin_mainnet", False),  # Solana to Bitcoin
        (
            Coin.BTC,
            "bitcoin_mainnet",
            Coin.BTC,
            "bitcoin_mainnet",
            False,
        ),  # Bitcoin to Bitcoin
        (Coin.SOL, "0x65", Coin.SOL, "0x65", False),  # Solana to Solana
    ],
)
async def test_has_support(
    client,
    source_coin,
    source_chain_id,
    dest_coin,
    dest_chain_id,
    expected,
):
    request = SwapSupportRequest(
        source_coin=source_coin,
        source_chain_id=source_chain_id,
        source_token_address=None,
        destination_coin=dest_coin,
        destination_chain_id=dest_chain_id,
        destination_token_address=None,
        recipient="0x1234567890123456789012345678901234567890",
    )

    result = await client.has_support(request)
    assert result is expected


@pytest.mark.asyncio
async def test_get_indicative_routes_success(
    client,
    mock_httpx_client,
    mock_token_manager,
):
    # Mock token manager to return tokens
    def token_get_side_effect(coin, chain_id, address):
        if chain_id == Chain.ETHEREUM.chain_id:
            if address is None:
                return ETH_ON_ETHEREUM_TOKEN_INFO
            elif address == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48":
                return USDC_ON_ETHEREUM_TOKEN_INFO
        elif chain_id == Chain.ARBITRUM.chain_id:
            if address is None:
                return ETH_ON_ARBITRUM_TOKEN_INFO
            elif address == "0xaf88d065e77c8cC2239327C5EDb3A432268e5831":
                return USDC_ON_ARBITRUM_TOKEN_INFO
        return None

    mock_token_manager.get = AsyncMock(side_effect=token_get_side_effect)

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SQUID_ROUTE_RESPONSE
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address=None,  # Native ETH
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        recipient="0x1234567890123456789012345678901234567890",
        amount="1000000000000000000",  # 1 ETH
        slippage_percentage="1.0",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0x1234567890123456789012345678901234567890",
        provider=SwapProviderEnum.SQUID,
    )

    routes = await client.get_indicative_routes(request)

    # Verify API was called
    mock_httpx_client.post.assert_called_once()
    call_args = mock_httpx_client.post.call_args
    assert "v2/route" in call_args[0][0]

    # Verify response is a list with one route
    assert isinstance(routes, list)
    assert len(routes) == 1

    route = routes[0]
    assert route.provider == SwapProviderEnum.SQUID
    assert len(route.steps) == 1  # Cross-chain swap is one step
    assert route.source_amount == "1000000000000000000"
    assert route.destination_amount == "1850000000"
    assert route.destination_amount_min == "1831500000"
    assert route.estimated_time == 180
    assert route.requires_token_allowance is True
    assert route.requires_firm_route is False
    assert route.has_post_submit_hook is False
    assert route.id == "squid-quote-12345abcde"


@pytest.mark.asyncio
async def test_get_firm_route_success(
    client,
    mock_httpx_client,
    mock_token_manager,
):
    # Mock token manager to return tokens
    def token_get_side_effect(coin, chain_id, address):
        if chain_id == Chain.ETHEREUM.chain_id and address is None:
            return ETH_ON_ETHEREUM_TOKEN_INFO
        elif (
            chain_id == Chain.ARBITRUM.chain_id
            and address == "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
        ):
            return USDC_ON_ARBITRUM_TOKEN_INFO
        return None

    mock_token_manager.get = AsyncMock(side_effect=token_get_side_effect)

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SQUID_ROUTE_RESPONSE
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address=None,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        recipient="0x1234567890123456789012345678901234567890",
        amount="1000000000000000000",
        slippage_percentage="1.0",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0x1234567890123456789012345678901234567890",
        provider=SwapProviderEnum.SQUID,
    )

    route = await client.get_firm_route(request)

    # Verify route has transaction params
    assert route.transaction_params is not None
    assert route.transaction_params.evm is not None
    assert (
        route.transaction_params.evm.to == "0xce16F69375520ab01377ce7B88f5BA8C48F8D666"
    )
    assert route.transaction_params.evm.data == "0x1234567890abcdef"
    assert route.transaction_params.evm.value == "1000000000000000000"
    assert route.transaction_params.evm.gas_limit == "300000"

    # Verify deposit address (for ERC20 approval)
    assert route.deposit_address == "0xce16F69375520ab01377ce7B88f5BA8C48F8D666"

    # Verify network fee
    assert route.network_fee is not None
    assert route.network_fee.amount == "50000000000000000"
    assert route.network_fee.symbol == "ETH"


@pytest.mark.asyncio
async def test_get_route_api_error(
    client,
    mock_httpx_client,
):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = MOCK_SQUID_ERROR_RESPONSE
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address=None,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        recipient="0x1234567890123456789012345678901234567890",
        amount="1000000000000000000",
        slippage_percentage="1.0",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0x1234567890123456789012345678901234567890",
        provider=SwapProviderEnum.SQUID,
    )

    with pytest.raises(SwapError) as exc_info:
        await client.get_indicative_routes(request)

    assert exc_info.value.kind == SwapErrorKind.INSUFFICIENT_LIQUIDITY
    assert "liquidity" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_get_status_success(
    client,
    mock_httpx_client,
):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SQUID_STATUS_SUCCESS
    mock_httpx_client.get.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        deposit_address="0xce16F69375520ab01377ce7B88f5BA8C48F8D666",
        provider=SwapProviderEnum.SQUID,
        id="squid-quote-12345abcde",
    )

    status = await client.get_status(request)

    assert status.status == SwapStatus.SUCCESS
    assert status.internal_status == "completed"


@pytest.mark.asyncio
async def test_get_status_ongoing(
    client,
    mock_httpx_client,
):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SQUID_STATUS_ONGOING
    mock_httpx_client.get.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        deposit_address="0xce16F69375520ab01377ce7B88f5BA8C48F8D666",
        provider=SwapProviderEnum.SQUID,
        id="test-route-id",
    )

    status = await client.get_status(request)

    assert status.status == SwapStatus.PROCESSING
    assert status.internal_status == "bridging"


@pytest.mark.asyncio
async def test_post_submit_hook_is_noop(client):
    """Test that post_submit_hook is a no-op."""
    request = SwapStatusRequest(
        tx_hash="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        deposit_address="0xce16F69375520ab01377ce7B88f5BA8C48F8D666",
        provider=SwapProviderEnum.SQUID,
        id="test-route-id",
    )

    # Should not raise any exception
    await client.post_submit_hook(request)


@pytest.mark.parametrize(
    "chain,expected",
    [
        # EVM chains - hex to decimal conversion
        (Chain.ETHEREUM, "1"),
        (Chain.ARBITRUM, "42161"),
        (Chain.AVALANCHE, "43114"),
        (Chain.OPTIMISM, "10"),
        (Chain.POLYGON, "137"),
        (Chain.BASE, "8453"),
        # Bitcoin
        (Chain.BITCOIN, "bitcoin"),
        # Solana
        (Chain.SOLANA, "solana-mainnet-beta"),
    ],
)
def test_get_squid_chain_id_from_chain(chain, expected):
    """Test get_squid_chain_id_from_chain function for EVM, Bitcoin, and Solana chains."""
    from .utils import get_squid_chain_id_from_chain

    result = get_squid_chain_id_from_chain(chain)
    assert result == expected
