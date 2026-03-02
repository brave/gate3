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

from .client import LifiClient
from .mocks import (
    MOCK_LIFI_ERROR_RESPONSE,
    MOCK_LIFI_QUOTE_RESPONSE,
    MOCK_LIFI_STATUS_DONE,
    MOCK_LIFI_STATUS_PENDING,
    MOCK_LIFI_TOKENS_RESPONSE,
)
from .models import LifiError
from .utils import categorize_error, get_lifi_chain_id


@pytest.fixture
def mock_token_manager():
    mock_manager = AsyncMock(spec=TokenManager)
    mock_manager.get = AsyncMock(return_value=None)
    return mock_manager


@pytest.fixture
def client(mock_token_manager):
    with patch("app.api.swap.providers.lifi.client.settings") as mock_settings:
        mock_settings.LIFI_API_KEY = "test_api_key"
        yield LifiClient(token_manager=mock_token_manager)


@pytest.fixture
def mock_httpx_client():
    with patch("app.api.swap.providers.lifi.client.create_http_client") as mock:
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
@pytest.mark.parametrize(
    "source_coin,source_chain_id,dest_coin,dest_chain_id,expected",
    [
        # EVM to EVM
        (Coin.ETH, "0x1", Coin.ETH, "0xa4b1", True),
        (Coin.ETH, "0xa4b1", Coin.ETH, "0x1", True),
        (Coin.ETH, "0x1", Coin.ETH, "0xa", True),
        (Coin.ETH, "0x89", Coin.ETH, "0x2105", True),
        # Same chain
        (Coin.ETH, "0x1", Coin.ETH, "0x1", True),
        # EVM to Solana and Bitcoin
        (Coin.ETH, "0x1", Coin.SOL, "0x65", True),
        (Coin.ETH, "0xa4b1", Coin.BTC, "bitcoin_mainnet", True),
        # Solana as source
        (Coin.SOL, "0x65", Coin.ETH, "0x1", True),
        # BTC as source not supported (LI.FI requires UTXO validation)
        (Coin.BTC, "bitcoin_mainnet", Coin.ETH, "0x1", False),
        (Coin.BTC, "bitcoin_mainnet", Coin.SOL, "0x65", False),
        # Unsupported chains
        (Coin.ADA, "cardano_mainnet", Coin.ETH, "0x1", False),
        (Coin.ETH, "0x1", Coin.ADA, "cardano_mainnet", False),
        (Coin.FIL, "f", Coin.ETH, "0x1", False),
        (Coin.ETH, "0x1", Coin.ZEC, "zcash_mainnet", False),
        # Unknown chain
        (Coin.ETH, "0xunknown", Coin.ETH, "0x1", False),
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
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LIFI_QUOTE_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address=None,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        recipient="0x1234567890123456789012345678901234567890",
        amount="1000000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0x1234567890123456789012345678901234567890",
        provider=SwapProviderEnum.LIFI,
    )

    routes = await client.get_indicative_routes(request)

    mock_httpx_client.get.assert_called_once()
    call_args = mock_httpx_client.get.call_args
    assert "quote" in call_args[0][0]

    params = call_args[1]["params"]
    assert params["integrator"] == "brave"

    assert isinstance(routes, list)
    assert len(routes) == 1

    route = routes[0]
    assert route.provider == SwapProviderEnum.LIFI
    assert len(route.steps) == 2  # Two included steps
    assert route.source_amount == "1000000000000000000"
    assert route.destination_amount == "1850000000"
    assert route.destination_amount_min == "1840750000"
    assert route.estimated_time == 180
    assert route.requires_token_allowance is False  # Native token, no allowance
    assert route.requires_firm_route is False
    assert route.id == "lifi-quote-12345abcde"


@pytest.mark.asyncio
async def test_get_firm_route_success(
    client,
    mock_httpx_client,
    mock_token_manager,
):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LIFI_QUOTE_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address=None,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        recipient="0x1234567890123456789012345678901234567890",
        amount="1000000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0x1234567890123456789012345678901234567890",
        provider=SwapProviderEnum.LIFI,
    )

    route = await client.get_firm_route(request)

    assert route.transaction_params is not None
    assert route.transaction_params.evm is not None
    assert (
        route.transaction_params.evm.to == "0xLifiDiamondContract12345678901234567890"
    )
    assert route.transaction_params.evm.data == "0xabcdef1234567890"
    assert route.transaction_params.evm.value == "1000000000000000000"
    assert route.transaction_params.evm.gas_limit == "400000"

    # Deposit address is the approval address
    assert route.deposit_address == "0xApprovalAddress1234567890123456789012345"

    # Network fee: 50000000000000000 gas cost (source chain gas)
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
    mock_response.json.return_value = MOCK_LIFI_ERROR_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address=None,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        recipient="0x1234567890123456789012345678901234567890",
        amount="1000000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0x1234567890123456789012345678901234567890",
        provider=SwapProviderEnum.LIFI,
    )

    with pytest.raises(SwapError) as exc_info:
        await client.get_indicative_routes(request)

    assert exc_info.value.kind == SwapErrorKind.INSUFFICIENT_LIQUIDITY
    assert "no possible route" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_get_status_success(
    client,
    mock_httpx_client,
):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LIFI_STATUS_DONE
    mock_httpx_client.get.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="0xabc123",
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        deposit_address="0xApprovalAddress1234567890123456789012345",
        provider=SwapProviderEnum.LIFI,
        route_id="lifi-quote-12345abcde",
    )

    status = await client.get_status(request)

    assert status.status == SwapStatus.SUCCESS
    assert status.internal_status == "COMPLETED"
    assert status.explorer_url == "https://explorer.li.fi/tx/0xabc123"


@pytest.mark.asyncio
async def test_get_status_pending(
    client,
    mock_httpx_client,
):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LIFI_STATUS_PENDING
    mock_httpx_client.get.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="0xabc123",
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        deposit_address="0xApprovalAddress1234567890123456789012345",
        provider=SwapProviderEnum.LIFI,
        route_id="lifi-quote-12345abcde",
    )

    status = await client.get_status(request)

    assert status.status == SwapStatus.PROCESSING


@pytest.mark.parametrize(
    "chain,expected",
    [
        (Chain.ETHEREUM, 1),
        (Chain.ARBITRUM, 42161),
        (Chain.AVALANCHE, 43114),
        (Chain.OPTIMISM, 10),
        (Chain.POLYGON, 137),
        (Chain.BASE, 8453),
        (Chain.BNB_CHAIN, 56),
        (Chain.SOLANA, 1151111081099710),
        (Chain.BITCOIN, 20000000000001),
    ],
)
def test_get_lifi_chain_id(chain, expected):
    result = get_lifi_chain_id(chain)
    assert result == expected


@pytest.mark.asyncio
async def test_network_fee_computation(
    client,
    mock_httpx_client,
    mock_token_manager,
):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LIFI_QUOTE_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address=None,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        recipient="0x1234567890123456789012345678901234567890",
        amount="1000000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0x1234567890123456789012345678901234567890",
        provider=SwapProviderEnum.LIFI,
    )

    route = await client.get_firm_route(request)

    # Gas cost from top-level estimate: 50000000000000000
    # tx value equals from_amount (native), so no excess fee
    assert route.network_fee is not None
    assert route.network_fee.amount == "50000000000000000"
    assert route.network_fee.decimals == 18
    assert route.network_fee.symbol == "ETH"


@pytest.mark.asyncio
async def test_get_supported_tokens(client, mock_httpx_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LIFI_TOKENS_RESPONSE
    mock_response.raise_for_status = MagicMock()
    mock_httpx_client.get.return_value = mock_response

    tokens = await client.get_supported_tokens()

    mock_httpx_client.get.assert_called_once()
    call_args = mock_httpx_client.get.call_args
    assert "tokens" in call_args[0][0]
    assert call_args[1]["params"]["chainTypes"] == "EVM,SVM,UTXO"

    # 7 known tokens (2 ETH + 2 ARB + 2 SOL + 1 BTC), unknown chain skipped
    assert len(tokens) == 7

    # Check native ETH on Ethereum (0x000...000 → None)
    eth_native = [t for t in tokens if t.chain == Chain.ETHEREUM and t.address is None]
    assert len(eth_native) == 1
    assert eth_native[0].symbol == "ETH"
    assert eth_native[0].decimals == 18
    assert eth_native[0].logo == "https://example.com/eth.png"

    # Check USDC on Arbitrum
    usdc_arb = [
        t
        for t in tokens
        if t.chain == Chain.ARBITRUM
        and t.address == "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
    ]
    assert len(usdc_arb) == 1
    assert usdc_arb[0].symbol == "USDC"
    assert usdc_arb[0].decimals == 6

    # Check native SOL on Solana (11111...111 → None)
    sol_native = [t for t in tokens if t.chain == Chain.SOLANA and t.address is None]
    assert len(sol_native) == 1
    assert sol_native[0].symbol == "SOL"
    assert sol_native[0].decimals == 9

    # Check USDC on Solana (non-native address preserved)
    usdc_sol = [
        t
        for t in tokens
        if t.chain == Chain.SOLANA
        and t.address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    ]
    assert len(usdc_sol) == 1
    assert usdc_sol[0].symbol == "USDC"

    # Check native BTC on Bitcoin ("bitcoin" → None)
    btc_native = [t for t in tokens if t.chain == Chain.BITCOIN and t.address is None]
    assert len(btc_native) == 1
    assert btc_native[0].symbol == "BTC"
    assert btc_native[0].decimals == 8


@pytest.mark.parametrize(
    "code,expected_kind",
    [
        (1000, SwapErrorKind.UNKNOWN),  # DefaultError
        (1001, SwapErrorKind.INVALID_REQUEST),  # FailedToBuildTransactionError
        (1002, SwapErrorKind.INSUFFICIENT_LIQUIDITY),  # NoQuoteError
        (1003, SwapErrorKind.INVALID_REQUEST),  # NotFoundError
        (1004, SwapErrorKind.INVALID_REQUEST),  # NotProcessableError
        (1005, SwapErrorKind.RATE_LIMIT_EXCEEDED),  # RateLimitError
        (1006, SwapErrorKind.UNKNOWN),  # ServerError
        (1007, SwapErrorKind.INVALID_REQUEST),  # SlippageError
        (1008, SwapErrorKind.UNKNOWN),  # ThirdPartyError
        (1009, SwapErrorKind.TIMEOUT),  # TimeoutError
        (1010, SwapErrorKind.INVALID_REQUEST),  # UnauthorizedError
        (1011, SwapErrorKind.INVALID_REQUEST),  # ValidationError
        (1012, SwapErrorKind.UNKNOWN),  # RpcFailure
        (1013, SwapErrorKind.INVALID_REQUEST),  # MalformedSchema
        (9999, SwapErrorKind.UNKNOWN),  # Unknown code falls through
        (None, SwapErrorKind.UNKNOWN),  # No code
    ],
)
def test_categorize_error(code, expected_kind):
    error = LifiError(message="test error", code=code)
    assert categorize_error(error) == expected_kind
