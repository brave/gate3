from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.common.models import Chain, Coin, TokenInfo, TokenSource, TokenType
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

from .client import ZeroExClient
from .constants import ZERO_EX_SUPPORTED_CHAINS
from .mocks import (
    MOCK_ALCHEMY_RECEIPT_FAILED,
    MOCK_ALCHEMY_RECEIPT_NULL,
    MOCK_ALCHEMY_RECEIPT_SUCCESS,
    MOCK_ZERO_EX_ERROR_404,
    MOCK_ZERO_EX_ERROR_429,
    MOCK_ZERO_EX_ERROR_VALIDATION,
    MOCK_ZERO_EX_NO_LIQUIDITY_RESPONSE,
    MOCK_ZERO_EX_QUOTE_ERC20_RESPONSE,
    MOCK_ZERO_EX_QUOTE_RESPONSE,
)
from .models import ZeroExError
from .utils import (
    categorize_error,
    convert_slippage_to_bps,
    get_zero_ex_chain_id,
    get_zero_ex_token_address,
)


@pytest.fixture
def mock_token_manager():
    mock_manager = AsyncMock(spec=TokenManager)
    mock_manager.get = AsyncMock(return_value=None)
    return mock_manager


@pytest.fixture
def client(mock_token_manager):
    with patch("app.api.swap.providers.zero_ex.client.settings") as mock_settings:
        mock_settings.ZERO_EX_API_KEY = "test_api_key"
        yield ZeroExClient(token_manager=mock_token_manager)


@pytest.fixture
def mock_httpx_client():
    with patch("app.api.swap.providers.zero_ex.client.create_http_client") as mock:
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


def _make_quote_request(**overrides) -> SwapQuoteRequest:
    base = {
        "source_coin": Chain.ARBITRUM.coin,
        "source_chain_id": Chain.ARBITRUM.chain_id,
        "source_token_address": None,
        "destination_coin": Chain.ARBITRUM.coin,
        "destination_chain_id": Chain.ARBITRUM.chain_id,
        "destination_token_address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "amount": "1000000000000000000",
        "slippage_percentage": "0.5",
        "swap_type": SwapType.EXACT_INPUT,
        "refund_to": "0xa92D461a9a988A7f11ec285d39783A637Fdd6ba4",
        "provider": SwapProviderEnum.ZERO_EX,
    }
    base.update(overrides)
    return SwapQuoteRequest(**base)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_coin,source_chain_id,source_addr,dest_coin,dest_chain_id,dest_addr,expected",
    [
        # Same chain, native -> ERC20 on each supported chain
        (
            Coin.ETH,
            "0x1",
            None,
            Coin.ETH,
            "0x1",
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            True,
        ),
        (
            Coin.ETH,
            "0xa4b1",
            None,
            Coin.ETH,
            "0xa4b1",
            "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            True,
        ),
        (
            Coin.ETH,
            "0xa86a",
            None,
            Coin.ETH,
            "0xa86a",
            "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
            True,
        ),
        (
            Coin.ETH,
            "0x2105",
            None,
            Coin.ETH,
            "0x2105",
            "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            True,
        ),
        (
            Coin.ETH,
            "0x38",
            None,
            Coin.ETH,
            "0x38",
            "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
            True,
        ),
        (
            Coin.ETH,
            "0xa",
            None,
            Coin.ETH,
            "0xa",
            "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
            True,
        ),
        (
            Coin.ETH,
            "0x89",
            None,
            Coin.ETH,
            "0x89",
            "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
            True,
        ),
        # ERC20 -> native (reverse direction)
        (
            Coin.ETH,
            "0xa4b1",
            "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            Coin.ETH,
            "0xa4b1",
            None,
            True,
        ),
        # Cross-chain rejected
        (Coin.ETH, "0x1", None, Coin.ETH, "0xa4b1", None, False),
        (Coin.ETH, "0xa4b1", None, Coin.ETH, "0x1", None, False),
        # Non-EVM rejected
        (Coin.SOL, "0x65", None, Coin.SOL, "0x65", None, False),
        (Coin.BTC, "bitcoin_mainnet", None, Coin.BTC, "bitcoin_mainnet", None, False),
        (Coin.ETH, "0x1", None, Coin.SOL, "0x65", None, False),
        # Unsupported EVM chain (Filecoin treated as ETH-like? no — different coin. But unknown chain_id case:)
        (Coin.ETH, "0xdead", None, Coin.ETH, "0xdead", None, False),
        # Identical tokens rejected
        (Coin.ETH, "0x1", None, Coin.ETH, "0x1", None, False),
        (
            Coin.ETH,
            "0x1",
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            Coin.ETH,
            "0x1",
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            False,
        ),
    ],
)
async def test_has_support(
    client,
    source_coin,
    source_chain_id,
    source_addr,
    dest_coin,
    dest_chain_id,
    dest_addr,
    expected,
):
    request = SwapSupportRequest(
        source_coin=source_coin,
        source_chain_id=source_chain_id,
        source_token_address=source_addr,
        destination_coin=dest_coin,
        destination_chain_id=dest_chain_id,
        destination_token_address=dest_addr,
        recipient="0x1234567890123456789012345678901234567890",
    )
    assert await client.has_support(request) is expected


@pytest.mark.asyncio
async def test_get_indicative_routes_success(client, mock_httpx_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_ZERO_EX_QUOTE_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ARBITRUM.coin,
        source_chain_id=Chain.ARBITRUM.chain_id,
        source_token_address=None,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        amount="1000000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0xa92D461a9a988A7f11ec285d39783A637Fdd6ba4",
        provider=SwapProviderEnum.ZERO_EX,
    )

    routes = await client.get_indicative_routes(request)

    mock_httpx_client.get.assert_called_once()
    call_args = mock_httpx_client.get.call_args
    assert "allowance-holder/quote" in call_args[0][0]

    params = call_args[1]["params"]
    assert params["chainId"] == 42161
    assert params["sellToken"] == "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
    assert params["buyToken"] == "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
    assert params["sellAmount"] == "1000000000000000000"
    assert params["taker"] == "0xa92D461a9a988A7f11ec285d39783A637Fdd6ba4"
    assert params["slippageBps"] == 50

    assert isinstance(routes, list)
    assert len(routes) == 1
    route = routes[0]
    assert route.provider == SwapProviderEnum.ZERO_EX
    assert route.source_amount == "1000000000000000000"
    assert route.destination_amount == "1850000000"
    assert route.destination_amount_min == "1840750000"
    assert route.requires_token_allowance is False  # native
    assert route.requires_firm_route is False
    assert len(route.steps) == 2  # two fills
    assert route.steps[0].tool.name == "Uniswap_V3"
    assert route.steps[0].percent == 70.0
    assert route.steps[1].tool.name == "Curve"
    assert route.steps[1].percent == 30.0


@pytest.mark.asyncio
async def test_get_firm_route_erc20(client, mock_httpx_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_ZERO_EX_QUOTE_ERC20_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address="0xdAC17F958D2ee523a2206206994597C13D831ec7",
        destination_coin=Chain.ETHEREUM.coin,
        destination_chain_id=Chain.ETHEREUM.chain_id,
        destination_token_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        amount="1000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0xa92D461a9a988A7f11ec285d39783A637Fdd6ba4",
        provider=SwapProviderEnum.ZERO_EX,
    )

    route = await client.get_firm_route(request)

    assert route.requires_token_allowance is True
    assert route.deposit_address == "0x0000000000001fF3684f28c67538d4D072C22734"
    assert route.transaction_params is not None
    assert route.transaction_params.evm is not None
    assert route.transaction_params.evm.data == "0xabcdef"
    assert route.transaction_params.evm.value == "0"
    assert route.transaction_params.evm.gas_limit == "250000"
    assert route.network_fee is not None
    assert route.network_fee.amount == "25000000000000000"
    assert route.network_fee.symbol == "ETH"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,payload,expected_kind",
    [
        (200, MOCK_ZERO_EX_NO_LIQUIDITY_RESPONSE, SwapErrorKind.INSUFFICIENT_LIQUIDITY),
        (404, MOCK_ZERO_EX_ERROR_404, SwapErrorKind.INSUFFICIENT_LIQUIDITY),
        (429, MOCK_ZERO_EX_ERROR_429, SwapErrorKind.RATE_LIMIT_EXCEEDED),
        (400, MOCK_ZERO_EX_ERROR_VALIDATION, SwapErrorKind.INVALID_REQUEST),
    ],
    ids=["no_liquidity_200", "not_found_404", "rate_limited_429", "validation_400"],
)
async def test_get_firm_route_errors_mapped(
    client, mock_httpx_client, status_code, payload, expected_kind
):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = payload
    mock_httpx_client.get.return_value = mock_response

    with pytest.raises(SwapError) as exc_info:
        await client.get_firm_route(_make_quote_request())

    assert exc_info.value.kind == expected_kind


@pytest.mark.asyncio
async def test_exact_output_rejected(client, mock_httpx_client):
    request = SwapQuoteRequest(
        source_coin=Chain.ARBITRUM.coin,
        source_chain_id=Chain.ARBITRUM.chain_id,
        source_token_address=None,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        amount="1000000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_OUTPUT,
        refund_to="0xa92D461a9a988A7f11ec285d39783A637Fdd6ba4",
        provider=SwapProviderEnum.ZERO_EX,
    )

    with pytest.raises(SwapError) as exc_info:
        await client.get_firm_route(request)

    assert exc_info.value.kind == SwapErrorKind.INVALID_REQUEST
    mock_httpx_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_recipient_different_from_refund_to_rejected(client, mock_httpx_client):
    request = SwapQuoteRequest(
        source_coin=Chain.ARBITRUM.coin,
        source_chain_id=Chain.ARBITRUM.chain_id,
        source_token_address=None,
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        recipient="0x0000000000000000000000000000000000000001",
        amount="1000000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0xa92D461a9a988A7f11ec285d39783A637Fdd6ba4",
        provider=SwapProviderEnum.ZERO_EX,
    )

    with pytest.raises(SwapError) as exc_info:
        await client.get_firm_route(request)

    assert exc_info.value.kind == SwapErrorKind.INVALID_REQUEST
    mock_httpx_client.get.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_addr,dest_addr,expected",
    [
        # Null source + 0x native sentinel dest is identity (both = native ETH)
        (None, "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE", False),
        # Native sentinel source + null dest is identity
        ("0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE", None, False),
        # Native sentinel source + ERC20 dest is a real swap
        (
            "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
            "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            True,
        ),
    ],
)
async def test_has_support_native_sentinel_identity(
    client, source_addr, dest_addr, expected
):
    request = SwapSupportRequest(
        source_coin=Coin.ETH,
        source_chain_id="0xa4b1",
        source_token_address=source_addr,
        destination_coin=Coin.ETH,
        destination_chain_id="0xa4b1",
        destination_token_address=dest_addr,
        recipient="0xa92D461a9a988A7f11ec285d39783A637Fdd6ba4",
    )
    assert await client.has_support(request) is expected


@pytest.mark.asyncio
async def test_get_firm_route_native_sentinel_source_no_allowance(
    client, mock_httpx_client
):
    """Native sentinel as source must not set requires_token_allowance."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_ZERO_EX_QUOTE_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ARBITRUM.coin,
        source_chain_id=Chain.ARBITRUM.chain_id,
        source_token_address="0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
        destination_coin=Chain.ARBITRUM.coin,
        destination_chain_id=Chain.ARBITRUM.chain_id,
        destination_token_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        amount="10000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0xa92D461a9a988A7f11ec285d39783A637Fdd6ba4",
        provider=SwapProviderEnum.ZERO_EX,
    )
    route = await client.get_firm_route(request)
    assert route.requires_token_allowance is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slippage,should_raise",
    [
        ("abc", True),
        ("-1", True),
        ("", True),
        ("   ", True),
        ("0.5", False),
        (" 0.5 ", False),
        ("1e-1", False),
    ],
)
async def test_invalid_slippage_rejected(
    client, mock_httpx_client, slippage, should_raise
):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_ZERO_EX_QUOTE_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = _make_quote_request(
        amount="10000000000000000", slippage_percentage=slippage
    )

    if should_raise:
        with pytest.raises(SwapError) as exc_info:
            await client.get_firm_route(request)
        assert exc_info.value.kind == SwapErrorKind.INVALID_REQUEST
    else:
        route = await client.get_firm_route(request)
        assert route.slippage_percentage == slippage.strip()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chain,tx_hash,receipt,expected_status,expected_explorer",
    [
        (
            Chain.ARBITRUM,
            "0xabc123",
            MOCK_ALCHEMY_RECEIPT_SUCCESS,
            SwapStatus.SUCCESS,
            "https://arbiscan.io/tx/0xabc123",
        ),
        (
            Chain.ETHEREUM,
            "0xdef456",
            MOCK_ALCHEMY_RECEIPT_FAILED,
            SwapStatus.FAILED,
            "https://etherscan.io/tx/0xdef456",
        ),
        (
            Chain.BASE,
            "0xpending",
            MOCK_ALCHEMY_RECEIPT_NULL,
            SwapStatus.PENDING,
            "https://basescan.org/tx/0xpending",
        ),
    ],
    ids=["success_arbitrum", "failed_ethereum", "pending_base"],
)
async def test_get_status(
    client, chain, tx_hash, receipt, expected_status, expected_explorer
):
    with (
        patch("app.api.common.evm.tx_status.create_http_client") as mock_create,
        patch("app.api.common.evm.utils.settings") as mock_settings,
    ):
        mock_settings.ALCHEMY_API_KEY = "test-key"

        mock_rpc_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = receipt
        mock_response.raise_for_status = MagicMock()
        mock_rpc_client.post.return_value = mock_response
        mock_create.return_value.__aenter__.return_value = mock_rpc_client

        request = SwapStatusRequest(
            tx_hash=tx_hash,
            source_coin=chain.coin,
            source_chain_id=chain.chain_id,
            destination_coin=chain.coin,
            destination_chain_id=chain.chain_id,
            deposit_address="0x0000000000001fF3684f28c67538d4D072C22734",
            provider=SwapProviderEnum.ZERO_EX,
            route_id=f"zero_ex_{tx_hash}",
        )

        status = await client.get_status(request)
        assert status.status == expected_status
        assert status.explorer_url == expected_explorer


@pytest.mark.asyncio
async def test_get_supported_tokens_uses_token_manager(client):
    arbitrum_token = TokenInfo(
        coin=Coin.ETH,
        chain_id=Chain.ARBITRUM.chain_id,
        address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        name="USD Coin",
        symbol="USDC",
        decimals=6,
        logo=None,
        sources=[TokenSource.COINGECKO],
        token_type=TokenType.ERC20,
    )
    ethereum_token = TokenInfo(
        coin=Coin.ETH,
        chain_id=Chain.ETHEREUM.chain_id,
        address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        name="USD Coin",
        symbol="USDC",
        decimals=6,
        logo=None,
        sources=[TokenSource.COINGECKO],
        token_type=TokenType.ERC20,
    )

    def list_tokens_side_effect(coin, chain_id):
        if chain_id == Chain.ARBITRUM.chain_id:
            return [arbitrum_token]
        if chain_id == Chain.ETHEREUM.chain_id:
            return [ethereum_token]
        return []

    with patch.object(
        TokenManager, "list_tokens", new=AsyncMock(side_effect=list_tokens_side_effect)
    ) as mock_list:
        tokens = await client.get_supported_tokens()

    assert mock_list.await_count == len(ZERO_EX_SUPPORTED_CHAINS)
    chain_ids_called = {
        call.args[1] if len(call.args) > 1 else call.kwargs["chain_id"]
        for call in mock_list.await_args_list
    }
    assert Chain.ARBITRUM.chain_id in chain_ids_called
    assert Chain.ETHEREUM.chain_id in chain_ids_called
    assert arbitrum_token in tokens
    assert ethereum_token in tokens


@pytest.mark.parametrize(
    "slippage,expected_bps",
    [
        ("0.5", 50),
        ("1", 100),
        ("0.1", 10),
        ("2.5", 250),
        (None, None),
        ("not-a-number", None),
    ],
)
def test_convert_slippage_to_bps(slippage, expected_bps):
    assert convert_slippage_to_bps(slippage) == expected_bps


@pytest.mark.parametrize(
    "chain,expected",
    [
        (Chain.ETHEREUM, 1),
        (Chain.ARBITRUM, 42161),
        (Chain.AVALANCHE, 43114),
        (Chain.BASE, 8453),
        (Chain.BNB_CHAIN, 56),
        (Chain.OPTIMISM, 10),
        (Chain.POLYGON, 137),
        (Chain.SOLANA, None),
        (Chain.BITCOIN, None),
        (None, None),
    ],
)
def test_get_zero_ex_chain_id(chain, expected):
    assert get_zero_ex_chain_id(chain) == expected


@pytest.mark.parametrize(
    "address,expected",
    [
        (None, "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"),
        (
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        ),
    ],
)
def test_get_zero_ex_token_address(address, expected):
    assert get_zero_ex_token_address(address) == expected


@pytest.mark.parametrize(
    "name,status_code,expected_kind",
    [
        ("VALIDATION_FAILED", 400, SwapErrorKind.INVALID_REQUEST),
        ("INPUT_INVALID", 400, SwapErrorKind.INVALID_REQUEST),
        ("INSUFFICIENT_LIQUIDITY", 404, SwapErrorKind.INSUFFICIENT_LIQUIDITY),
        ("SWAP_VALIDATION_FAILED", 400, SwapErrorKind.INSUFFICIENT_LIQUIDITY),
        ("RATE_LIMITED", 429, SwapErrorKind.RATE_LIMIT_EXCEEDED),
        ("TOKEN_NOT_SUPPORTED", 400, SwapErrorKind.UNSUPPORTED_TOKENS),
        ("UNAUTHORIZED", 401, SwapErrorKind.INVALID_REQUEST),
        ("GATEWAY_TIMEOUT", 504, SwapErrorKind.TIMEOUT),
        (None, 404, SwapErrorKind.INSUFFICIENT_LIQUIDITY),
        (None, 429, SwapErrorKind.RATE_LIMIT_EXCEEDED),
        (None, 500, SwapErrorKind.UNKNOWN),
        (None, 400, SwapErrorKind.INVALID_REQUEST),
        (None, None, SwapErrorKind.UNKNOWN),
        ("UNKNOWN_ERROR_NAME", None, SwapErrorKind.UNKNOWN),
    ],
)
def test_categorize_error(name, status_code, expected_kind):
    error = ZeroExError(name=name, message="test")
    assert categorize_error(error, status_code) == expected_kind
