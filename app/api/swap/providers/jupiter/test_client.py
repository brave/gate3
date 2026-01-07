from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.common.models import Chain, TokenInfo, TokenSource, TokenType
from app.api.swap.models import (
    SwapError,
    SwapErrorKind,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapSupportRequest,
    SwapType,
)
from app.api.tokens.manager import TokenManager

from .client import JupiterClient
from .mocks import (
    MOCK_JUPITER_ORDER_RESPONSE,
    SOL_TOKEN_INFO,
    USDC_ON_SOLANA_TOKEN_INFO,
)


@pytest.fixture
def mock_token_manager():
    mock_manager = AsyncMock(spec=TokenManager)
    # Default behavior: return None (token not found)
    mock_manager.get = AsyncMock(return_value=None)
    return mock_manager


@pytest.fixture
def client(mock_token_manager):
    with patch("app.api.swap.providers.jupiter.client.settings") as mock_settings:
        mock_settings.JUPITER_API_KEY = "test_api_key"
        yield JupiterClient(token_manager=mock_token_manager)


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
    "source_coin,source_chain_id,expected",
    [
        # Success case: Solana to Solana swap
        (Chain.SOLANA.coin, Chain.SOLANA.chain_id, True),
        # Wrong chain: Ethereum to Solana
        (Chain.ETHEREUM.coin, Chain.ETHEREUM.chain_id, False),
        # Missing chain: Invalid chain_id
        (Chain.SOLANA.coin, "invalid_chain", False),
    ],
)
async def test_has_support(
    client,
    source_coin,
    source_chain_id,
    expected,
):
    request = SwapSupportRequest(
        source_coin=source_coin,
        source_chain_id=source_chain_id,
        source_token_address=None,
        destination_coin=Chain.SOLANA.coin,
        destination_chain_id=Chain.SOLANA.chain_id,
        destination_token_address=None,
        recipient="11111111111111111111111111111111",
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
        if address == "So11111111111111111111111111111111111111112" or address is None:
            return SOL_TOKEN_INFO
        elif address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
            return USDC_ON_SOLANA_TOKEN_INFO
        elif address == "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB":
            # Intermediate token in the route
            return TokenInfo(
                coin=Chain.SOLANA.coin,
                chain_id=Chain.SOLANA.chain_id,
                address="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                name="USDT",
                symbol="USDT",
                decimals=6,
                logo=None,
                sources=[TokenSource.UNKNOWN],
                token_type=TokenType.SPL_TOKEN,
            )
        return None

    mock_token_manager.get = AsyncMock(side_effect=token_get_side_effect)

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_JUPITER_ORDER_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address=None,  # Native SOL
        destination_coin=Chain.SOLANA.coin,
        destination_chain_id=Chain.SOLANA.chain_id,
        destination_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        recipient="11111111111111111111111111111111",
        amount="100000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="11111111111111111111111111111111",
        provider=SwapProviderEnum.JUPITER,
    )

    routes = await client.get_indicative_routes(request)

    # Verify API was called
    mock_httpx_client.get.assert_called_once()
    call_args = mock_httpx_client.get.call_args
    assert "ultra/v1/order" in call_args[0][0]
    assert "inputMint" in str(call_args[1]["params"])

    # Verify response is a list with one route
    assert isinstance(routes, list)
    assert len(routes) == 1

    route = routes[0]
    assert route.provider == SwapProviderEnum.JUPITER
    assert len(route.steps) == 2  # Two hops in the mock response
    assert route.source_amount == "100000000"
    assert route.destination_amount == "13882709"
    assert route.estimated_time == 0  # Jupiter swaps are atomic


@pytest.mark.asyncio
async def test_get_firm_route_success(
    client,
    mock_httpx_client,
    mock_token_manager,
):
    # Mock token manager to return tokens
    def token_get_side_effect(coin, chain_id, address):
        if address == "So11111111111111111111111111111111111111112" or address is None:
            return SOL_TOKEN_INFO
        elif address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
            return USDC_ON_SOLANA_TOKEN_INFO
        elif address == "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB":
            # Intermediate token in the route
            return TokenInfo(
                coin=Chain.SOLANA.coin,
                chain_id=Chain.SOLANA.chain_id,
                address="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                name="USDT",
                symbol="USDT",
                decimals=6,
                logo=None,
                sources=[TokenSource.UNKNOWN],
                token_type=TokenType.SPL_TOKEN,
            )
        return None

    mock_token_manager.get = AsyncMock(side_effect=token_get_side_effect)

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_JUPITER_ORDER_RESPONSE
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address=None,
        destination_coin=Chain.SOLANA.coin,
        destination_chain_id=Chain.SOLANA.chain_id,
        destination_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        recipient="11111111111111111111111111111111",
        amount="100000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="11111111111111111111111111111111",
        provider=SwapProviderEnum.JUPITER,
    )

    route = await client.get_firm_route(request)

    # Verify route steps
    assert len(route.steps) == 2
    assert route.steps[0].source_token.symbol == "SOL"
    assert route.steps[0].destination_token.symbol == "USDT"
    assert route.steps[1].source_token.symbol == "USDT"
    assert route.steps[1].destination_token.symbol == "USDC"

    # Verify route has transaction params
    assert route.transaction_params is not None
    assert route.transaction_params.solana is not None
    assert route.transaction_params.solana.versioned_transaction is not None


@pytest.mark.asyncio
async def test_get_order_api_error(
    client,
    mock_httpx_client,
):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "Invalid parameters"}
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address=None,
        destination_coin=Chain.SOLANA.coin,
        destination_chain_id=Chain.SOLANA.chain_id,
        destination_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        recipient="11111111111111111111111111111111",
        amount="100000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="11111111111111111111111111111111",
        provider=SwapProviderEnum.JUPITER,
    )

    with pytest.raises(SwapError) as exc_info:
        await client.get_indicative_routes(request)

        assert exc_info.value.kind == SwapErrorKind.UNKNOWN
        assert "Invalid parameters" in exc_info.value.message


@pytest.mark.asyncio
async def test_get_order_with_error_in_response(
    client,
    mock_httpx_client,
):
    # Mock API response with error
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        **MOCK_JUPITER_ORDER_RESPONSE,
        "error": "Insufficient liquidity",
        "errorCode": 1,
    }
    mock_httpx_client.get.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address=None,
        destination_coin=Chain.SOLANA.coin,
        destination_chain_id=Chain.SOLANA.chain_id,
        destination_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        recipient="11111111111111111111111111111111",
        amount="100000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="11111111111111111111111111111111",
        provider=SwapProviderEnum.JUPITER,
    )

    with pytest.raises(SwapError) as exc_info:
        await client.get_indicative_routes(request)

        assert exc_info.value.kind == SwapErrorKind.INSUFFICIENT_LIQUIDITY
        assert "Insufficient liquidity" in exc_info.value.message
