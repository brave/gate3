from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
    TransactionParams,
)

from .client import NearIntentsClient
from .mocks import (
    ADA_TOKEN_INFO,
    BTC_TOKEN_DATA,
    BTC_TOKEN_INFO,
    ETH_TOKEN_INFO,
    FIL_TOKEN_INFO,
    MOCK_EXACT_OUTPUT_FIRM_QUOTE,
    MOCK_EXACT_OUTPUT_INDICATIVE_QUOTE,
    MOCK_EXACT_OUTPUT_QUOTE_REQUEST,
    MOCK_FIRM_QUOTE,
    MOCK_INDICATIVE_QUOTE,
    MOCK_QUOTE_REQUEST,
    SOL_TOKEN_INFO,
    USDC_ON_ETHEREUM_TOKEN_INFO,
    USDC_ON_SOLANA_TOKEN_DATA,
    USDC_ON_SOLANA_TOKEN_INFO,
    ZEC_TOKEN_INFO,
)


@pytest.fixture
def client():
    with patch("app.api.swap.providers.near_intents.client.settings") as mock_settings:
        mock_settings.NEAR_INTENTS_BASE_URL = "https://1click.chaindefuser.com"
        mock_settings.NEAR_INTENTS_JWT = "test_jwt_token"
        yield NearIntentsClient()


@pytest.fixture
def mock_httpx_client():
    with patch("httpx.AsyncClient") as mock:
        mock_client = AsyncMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock.return_value = mock_context
        yield mock_client


@pytest.fixture
def mock_supported_tokens_cache():
    with patch(
        "app.api.swap.providers.near_intents.client.SupportedTokensCache",
    ) as mock_cache:
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        yield mock_cache


@pytest.mark.asyncio
async def test_get_supported_tokens_from_api(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock API response
    mock_response = MagicMock()
    mock_response.json.return_value = [
        USDC_ON_SOLANA_TOKEN_DATA,
        BTC_TOKEN_DATA,
    ]
    mock_response.raise_for_status.return_value = None
    mock_httpx_client.get.return_value = mock_response

    tokens = await client.get_supported_tokens()

    # Verify API was called
    mock_httpx_client.get.assert_called_once_with(
        "https://1click.chaindefuser.com/v0/tokens",
    )

    # Verify cache was set
    mock_supported_tokens_cache.set.assert_called_once()

    # Verify tokens were parsed
    assert len(tokens) == 2
    (usdc, btc) = tokens

    assert usdc is not None
    assert usdc.coin == Coin.SOL
    assert usdc.chain_id == "0x65"
    assert usdc.address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    assert usdc.symbol == "USDC"
    assert usdc.decimals == 6
    assert (
        usdc.near_intents_asset_id
        == "nep141:sol-5ce3bf3a31af18be40ba30f721101b4341690186.omft.near"
    )

    assert btc is not None
    assert btc.coin == Coin.BTC
    assert btc.chain_id == "bitcoin_mainnet"
    assert btc.address is None
    assert btc.symbol == "BTC"
    assert btc.decimals == 8
    assert btc.near_intents_asset_id == "nep141:btc.omft.near"


@pytest.mark.asyncio
async def test_get_supported_tokens_from_cache(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    cached_tokens = [USDC_ON_SOLANA_TOKEN_INFO]
    mock_supported_tokens_cache.get.return_value = cached_tokens

    tokens = await client.get_supported_tokens()

    # Verify cache was checked
    mock_supported_tokens_cache.get.assert_called_once_with(
        SwapProviderEnum.NEAR_INTENTS,
    )

    # Verify API was NOT called
    mock_httpx_client.get.assert_not_called()

    # Verify cached tokens were returned
    assert tokens == cached_tokens


@pytest.mark.asyncio
async def test_get_supported_tokens_http_error(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found",
        request=MagicMock(),
        response=MagicMock(status_code=404),
    )
    mock_httpx_client.get.return_value = mock_response

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_supported_tokens()


@pytest.mark.asyncio
async def test_has_support_success(client, mock_supported_tokens_cache):
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    request = SwapSupportRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.has_support(request)

    assert result is True


@pytest.mark.asyncio
async def test_has_support_missing_chain(client):
    request = SwapSupportRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id="invalid_chain",
        source_token_address=None,
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
    )

    result = await client.has_support(request)

    assert result is False


@pytest.mark.asyncio
async def test_has_support_no_near_intents_id(client):
    # Use a chain that has no near_intents_id
    request = SwapSupportRequest(
        source_coin=Chain.FILECOIN.coin,
        source_chain_id=Chain.FILECOIN.chain_id,
        source_token_address=None,
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
    )

    result = await client.has_support(request)

    assert result is False


@pytest.mark.asyncio
async def test_has_support_token_not_supported(client, mock_supported_tokens_cache):
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    request = SwapSupportRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="UNSUPPORTED_TOKEN",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
    )

    result = await client.has_support(request)

    assert result is False


@pytest.mark.asyncio
async def test_handle_error_response(client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"message": "Invalid swap parameters"}

    with pytest.raises(SwapError) as exc_info:
        client._handle_error_response(mock_response)

    assert exc_info.value.message == "Invalid swap parameters"
    assert exc_info.value.kind == SwapErrorKind.UNKNOWN


@pytest.mark.asyncio
async def test_get_indicative_route_success(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock supported tokens
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": MOCK_QUOTE_REQUEST,
        "quote": MOCK_INDICATIVE_QUOTE,
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="2037265",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    routes = await client.get_indicative_routes(request)

    # Verify API was called
    mock_httpx_client.post.assert_called_once()
    call_args = mock_httpx_client.post.call_args
    assert call_args[0][0] == "https://1click.chaindefuser.com/v0/quote"
    assert call_args[1]["json"]["dry"] is True

    # Verify response is a list with one route
    assert len(routes) == 1
    result = routes[0]
    assert result.provider == SwapProviderEnum.NEAR_INTENTS
    assert result.source_amount == "2037265"
    assert result.destination_amount == "711"
    assert result.deposit_address is None  # Indicative quote has no deposit address
    # Deadline not set, so expires_at should be None
    assert result.expires_at is None

    # Verify route has steps
    assert len(result.steps) == 1
    step = result.steps[0]
    assert step.source_token.symbol == "USDC"
    assert step.destination_token.symbol == "BTC"
    assert step.source_amount == "2037265"
    assert step.destination_amount == "711"
    assert step.tool.name == "NEAR Intents"

    # Verify price impact calculation
    # amountInUsd: 2.0373, amountOutUsd: 0.6546
    # price_impact = (0.6546 / 2.0373 - 1) * 100 ≈ -67.87
    assert result.price_impact is not None
    assert result.price_impact == pytest.approx(-67.87, abs=0.1)

    # Indicative quotes don't have transaction params
    assert result.transaction_params is None


@pytest.mark.asyncio
async def test_get_firm_route_solana_native_sol(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock supported tokens - native SOL and BTC
    supported_tokens = [
        SOL_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": {
            **MOCK_QUOTE_REQUEST,
            "dry": False,
            "originAsset": "nep141:sol.omft.near",
        },
        "quote": {
            **MOCK_FIRM_QUOTE,
            "amountIn": "1000000000",  # 1 SOL in lamports
        },
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address=None,  # Native SOL
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="1000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_firm_route(request)

    # Verify transaction params for native SOL transfer
    assert result.transaction_params is not None

    # Verify that only one field under TransactionParams is not None
    assert result.transaction_params.solana is not None
    not_none_fields = [
        name
        for name in TransactionParams.model_fields
        if getattr(result.transaction_params, name) is not None
    ]
    assert len(not_none_fields) == 1

    assert (
        result.transaction_params.solana.from_address
        == "8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT"
    )
    assert (
        result.transaction_params.solana.to
        == "9RdSjLtfFJLvj6CAR4w7H7tUbv2kvwkkrYZuoojKDBkE"
    )
    assert result.transaction_params.solana.value == "1000000000"
    assert result.transaction_params.solana.spl_token_mint is None
    assert result.transaction_params.solana.spl_token_amount is None
    assert result.transaction_params.solana.decimals is None

    # Verify network fee is computed on the route
    assert result.network_fee is not None
    assert result.network_fee.symbol == "SOL"
    assert result.network_fee.decimals == 9


@pytest.mark.asyncio
async def test_get_firm_route_solana_spl_token(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock supported tokens - SPL token (USDC) and BTC
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": {**MOCK_QUOTE_REQUEST, "dry": False},
        "quote": MOCK_FIRM_QUOTE,
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # SPL token
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="2037265",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_firm_route(request)

    # Verify API was called
    mock_httpx_client.post.assert_called_once()
    call_args = mock_httpx_client.post.call_args
    assert call_args[0][0] == "https://1click.chaindefuser.com/v0/quote"
    assert call_args[1]["json"]["dry"] is False

    # Verify response
    assert result.provider == SwapProviderEnum.NEAR_INTENTS
    assert result.source_amount == "2037265"
    assert result.destination_amount == "711"
    assert result.deposit_address == "9RdSjLtfFJLvj6CAR4w7H7tUbv2kvwkkrYZuoojKDBkE"
    # Verify expires_at is a Unix timestamp string (not datetime)
    assert result.expires_at is not None
    assert isinstance(result.expires_at, str)
    # Verify it's a valid Unix timestamp (numeric string)
    assert result.expires_at.isdigit()
    # Verify it matches the expected timestamp from the mock deadline
    # Mock deadline: "2025-12-11T13:48:50.883000Z"
    expected_timestamp = str(
        int(
            datetime.fromisoformat(
                MOCK_FIRM_QUOTE["deadline"].replace("Z", "+00:00")
            ).timestamp()
        )
    )
    assert result.expires_at == expected_timestamp

    # Verify price impact calculation
    # amountInUsd: 2.0373, amountOutUsd: 0.6546
    # price_impact = (0.6546 / 2.0373 - 1) * 100 ≈ -67.87
    assert result.price_impact is not None
    assert result.price_impact == pytest.approx(-67.87, abs=0.1)

    # Verify transaction params for Solana SPL token transfer
    assert result.transaction_params is not None

    # Verify that only one field under TransactionParams is not None
    assert result.transaction_params.solana is not None
    not_none_fields = [
        name
        for name in TransactionParams.model_fields
        if getattr(result.transaction_params, name) is not None
    ]
    assert len(not_none_fields) == 1

    assert (
        result.transaction_params.solana.from_address
        == "8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT"
    )
    assert (
        result.transaction_params.solana.to
        == "9RdSjLtfFJLvj6CAR4w7H7tUbv2kvwkkrYZuoojKDBkE"
    )
    assert result.transaction_params.solana.value == "0"
    assert (
        result.transaction_params.solana.spl_token_mint
        == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    )
    assert result.transaction_params.solana.spl_token_amount == "2037265"
    assert result.transaction_params.solana.decimals == 6

    # Verify network fee is computed on the route
    assert result.network_fee is not None
    assert result.network_fee.symbol == "SOL"
    assert result.network_fee.decimals == 9


@pytest.mark.asyncio
@patch(
    "app.api.swap.providers.near_intents.utils.get_evm_gas_price",
    new_callable=AsyncMock,
)
async def test_get_firm_route_evm_native_eth(
    mock_get_evm_gas_price,
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock gas price to 1 wei so fee = gas_limit * 1 = gas_limit
    mock_get_evm_gas_price.return_value = 1

    # Mock supported tokens - native ETH and BTC
    supported_tokens = [
        ETH_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    deposit_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
    mock_response.json.return_value = {
        "quoteRequest": {
            **MOCK_QUOTE_REQUEST,
            "dry": False,
            "originAsset": "nep141:eth.omft.near",
        },
        "quote": {
            **MOCK_FIRM_QUOTE,
            "amountIn": "1000000000000000000",  # 1 ETH in wei
            "depositAddress": deposit_address,
        },
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address=None,  # Native ETH
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="1000000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0x8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_firm_route(request)

    # Verify transaction params for native ETH transfer
    assert result.transaction_params is not None

    # Verify that only one field under TransactionParams is not None
    assert result.transaction_params.evm is not None
    not_none_fields = [
        name
        for name in TransactionParams.model_fields
        if getattr(result.transaction_params, name) is not None
    ]
    assert len(not_none_fields) == 1

    assert (
        result.transaction_params.evm.from_address
        == "0x8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT"
    )
    assert result.transaction_params.evm.to == deposit_address
    assert result.transaction_params.evm.value == "1000000000000000000"
    assert result.transaction_params.evm.data == "0x"

    # Verify network fee is computed on the route
    assert result.network_fee is not None
    assert result.network_fee.amount == "21000"  # Native transfer gas limit * 1 wei
    assert result.network_fee.symbol == Chain.ETHEREUM.symbol
    assert result.network_fee.decimals == Chain.ETHEREUM.decimals


@pytest.mark.asyncio
@patch(
    "app.api.swap.providers.near_intents.transformations.estimate_gas_limit",
    new_callable=AsyncMock,
)
@patch(
    "app.api.swap.providers.near_intents.utils.get_evm_gas_price",
    new_callable=AsyncMock,
)
async def test_get_firm_route_evm_erc20_token(
    mock_get_evm_gas_price,
    mock_estimate_gas_limit,
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock gas price to 1 wei so fee = gas_limit * 1 = gas_limit
    mock_get_evm_gas_price.return_value = 1
    # Mock gas limit estimation to return the expected value for ERC20 transfers
    mock_estimate_gas_limit.return_value = 65000

    # Mock supported tokens - ERC20 USDC and BTC
    supported_tokens = [
        USDC_ON_ETHEREUM_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    deposit_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
    mock_response.json.return_value = {
        "quoteRequest": {
            **MOCK_QUOTE_REQUEST,
            "dry": False,
            "originAsset": "nep141:eth-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.omft.near",
        },
        "quote": {
            **MOCK_FIRM_QUOTE,
            "amountIn": "1000000",  # 1 USDC (6 decimals)
            "depositAddress": deposit_address,
        },
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ETHEREUM.coin,
        source_chain_id=Chain.ETHEREUM.chain_id,
        source_token_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="1000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="0x8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_firm_route(request)

    # Verify transaction params for ERC20 token transfer
    assert result.transaction_params is not None

    # Verify that only one field under TransactionParams is not None
    assert result.transaction_params.evm is not None
    not_none_fields = [
        name
        for name in TransactionParams.model_fields
        if getattr(result.transaction_params, name) is not None
    ]
    assert len(not_none_fields) == 1

    assert (
        result.transaction_params.evm.from_address
        == "0x8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT"
    )
    assert (
        result.transaction_params.evm.to == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    )  # Token contract
    assert result.transaction_params.evm.value == "0"
    assert result.transaction_params.evm.data.startswith(
        "0xa9059cbb",
    )  # transfer function selector
    assert len(result.transaction_params.evm.data) == 138

    # Verify network fee is computed on the route
    assert result.network_fee is not None
    assert result.network_fee.amount == "65000"  # ERC20 transfer gas limit * 1 wei
    assert result.network_fee.symbol == Chain.ETHEREUM.symbol
    assert result.network_fee.decimals == Chain.ETHEREUM.decimals


@pytest.mark.asyncio
async def test_get_firm_route_bitcoin(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock supported tokens - BTC and SOL
    supported_tokens = [
        BTC_TOKEN_INFO,
        USDC_ON_SOLANA_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    deposit_address = "bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn"
    mock_response.json.return_value = {
        "quoteRequest": {
            **MOCK_QUOTE_REQUEST,
            "dry": False,
            "originAsset": "nep141:btc.omft.near",
            "destinationAsset": "nep141:sol-5ce3bf3a31af18be40ba30f721101b4341690186.omft.near",
        },
        "quote": {
            **MOCK_FIRM_QUOTE,
            "amountIn": "100000",  # 0.001 BTC (8 decimals)
            "depositAddress": deposit_address,
        },
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.BITCOIN.coin,
        source_chain_id=Chain.BITCOIN.chain_id,
        source_token_address=None,  # Native BTC
        destination_coin=Chain.SOLANA.coin,
        destination_chain_id=Chain.SOLANA.chain_id,
        destination_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        recipient="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        amount="100000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_firm_route(request)

    # Verify transaction params for Bitcoin
    assert result.transaction_params is not None

    # Verify that only one field under TransactionParams is not None
    assert result.transaction_params.bitcoin is not None
    not_none_fields = [
        name
        for name in TransactionParams.model_fields
        if getattr(result.transaction_params, name) is not None
    ]
    assert len(not_none_fields) == 1

    assert result.transaction_params.bitcoin.to == deposit_address
    assert result.transaction_params.bitcoin.value == "100000"
    assert (
        result.transaction_params.bitcoin.refund_to
        == "bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn"
    )


@pytest.mark.asyncio
async def test_get_firm_route_zcash(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock supported tokens - ZEC and BTC
    supported_tokens = [
        ZEC_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    deposit_address = "t1ZCashDepositAddress123456789"
    mock_response.json.return_value = {
        "quoteRequest": {
            **MOCK_QUOTE_REQUEST,
            "dry": False,
            "originAsset": "nep141:zec.omft.near",
        },
        "quote": {
            **MOCK_FIRM_QUOTE,
            "amountIn": "100000000",  # 1 ZEC (8 decimals)
            "depositAddress": deposit_address,
        },
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.ZCASH.coin,
        source_chain_id=Chain.ZCASH.chain_id,
        source_token_address=None,  # Native ZEC
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="100000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="t1ZCashRefundAddress123456789",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_firm_route(request)

    # Verify transaction params for Zcash
    assert result.transaction_params is not None

    # Verify that only one field under TransactionParams is not None
    assert result.transaction_params.zcash is not None
    not_none_fields = [
        name
        for name in TransactionParams.model_fields
        if getattr(result.transaction_params, name) is not None
    ]
    assert len(not_none_fields) == 1

    assert result.transaction_params.zcash.to == deposit_address
    assert result.transaction_params.zcash.value == "100000000"
    assert result.transaction_params.zcash.refund_to == "t1ZCashRefundAddress123456789"


@pytest.mark.asyncio
async def test_get_firm_route_cardano(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock supported tokens - ADA and BTC
    supported_tokens = [
        ADA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    deposit_address = "addr1qyCardanoDepositAddress123456789"
    mock_response.json.return_value = {
        "quoteRequest": {
            **MOCK_QUOTE_REQUEST,
            "dry": False,
            "originAsset": "nep141:ada.omft.near",
        },
        "quote": {
            **MOCK_FIRM_QUOTE,
            "amountIn": "1000000",  # 1 ADA (6 decimals)
            "depositAddress": deposit_address,
        },
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.CARDANO.coin,
        source_chain_id=Chain.CARDANO.chain_id,
        source_token_address=None,  # Native ADA
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="1000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="addr1qyCardanoRefundAddress123456789",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_firm_route(request)

    # Verify transaction params for Cardano
    assert result.transaction_params is not None

    # Verify that only one field under TransactionParams is not None
    assert result.transaction_params.cardano is not None
    not_none_fields = [
        name
        for name in TransactionParams.model_fields
        if getattr(result.transaction_params, name) is not None
    ]
    assert len(not_none_fields) == 1

    assert result.transaction_params.cardano.to == deposit_address
    assert result.transaction_params.cardano.value == "1000000"
    assert (
        result.transaction_params.cardano.refund_to
        == "addr1qyCardanoRefundAddress123456789"
    )


@pytest.mark.asyncio
async def test_get_firm_route_unsupported_chain_raises_not_implemented(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock supported tokens - FIL (unsupported chain) and BTC
    # Filecoin has near_intents_id=None, so it's not supported by Near Intents
    supported_tokens = [
        FIL_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Note: We don't need to mock the API response because the error
    # will be raised in to_near_intents_request before the API is called

    request = SwapQuoteRequest(
        source_coin=Chain.FILECOIN.coin,
        source_chain_id=Chain.FILECOIN.chain_id,
        source_token_address=None,  # Native FIL
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="1000000000000000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="f1FilecoinRefundAddress123456789",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    # The error should be raised in to_near_intents_request because
    # Filecoin doesn't have near_intents_id support (it's None)
    with pytest.raises(ValueError) as exc_info:
        await client.get_firm_route(request)

    assert "Invalid source or destination chain" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_route_error_response(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock error response
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"message": "Invalid swap parameters"}
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="2037265",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    with pytest.raises(SwapError) as exc_info:
        await client.get_indicative_routes(request)

    assert exc_info.value.message == "Invalid swap parameters"
    assert exc_info.value.kind == SwapErrorKind.UNKNOWN


@pytest.mark.asyncio
async def test_get_status_success(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    """SUCCESS status returns correct response and does not submit deposit."""
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "SUCCESS"}
    mock_httpx_client.get.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="test_hash",
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        deposit_address="4Rqnz7SPU4EqSUravxbKTSBti4RNf1XGaqvBmnLfvH83",
        deposit_memo=None,
        provider=SwapProviderEnum.NEAR_INTENTS,
        route_id="test-route-id",
    )

    result = await client.get_status(request)

    # Verify API call
    mock_httpx_client.get.assert_called_once_with(
        "https://1click.chaindefuser.com/v0/status",
        params={"depositAddress": request.deposit_address},
    )

    # Verify no deposit submission for SUCCESS status
    mock_httpx_client.post.assert_not_called()

    # Verify response
    assert result.status == SwapStatus.SUCCESS
    assert result.internal_status == "SUCCESS"
    assert (
        result.explorer_url
        == "https://explorer.near-intents.org/transactions/4Rqnz7SPU4EqSUravxbKTSBti4RNf1XGaqvBmnLfvH83"
    )


@pytest.mark.asyncio
async def test_get_status_with_memo(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    # Mock supported tokens to avoid API call
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock GET response for status check
    mock_get_response = MagicMock()
    mock_get_response.status_code = 200
    mock_get_response.json.return_value = {"status": "PENDING_DEPOSIT"}
    mock_httpx_client.get.return_value = mock_get_response

    # Mock POST response for deposit submission (called when status is PENDING_DEPOSIT)
    mock_post_response = MagicMock()
    mock_post_response.status_code = 200
    mock_httpx_client.post.return_value = mock_post_response

    request = SwapStatusRequest(
        tx_hash="test_hash",
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        deposit_address="memo_test_unique_addr_xyz789",
        deposit_memo="test_memo",
        provider=SwapProviderEnum.NEAR_INTENTS,
        route_id="test-route-id",
    )

    result = await client.get_status(request)

    # Verify GET params include memo
    mock_httpx_client.get.assert_called_once_with(
        "https://1click.chaindefuser.com/v0/status",
        params={"depositAddress": request.deposit_address, "depositMemo": "test_memo"},
    )

    # Verify POST body includes memo
    mock_httpx_client.post.assert_called_once_with(
        "https://1click.chaindefuser.com/v0/deposit/submit",
        json={
            "txHash": request.tx_hash,
            "depositAddress": request.deposit_address,
            "memo": "test_memo",
        },
    )

    assert result.status == SwapStatus.PENDING
    assert result.internal_status == "PENDING_DEPOSIT"


@pytest.mark.asyncio
async def test_get_status_pending_deposit_empty_tx_hash_skips_submit(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    """When status is PENDING_DEPOSIT but tx_hash is empty, skip deposit submission."""
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    mock_get_response = MagicMock()
    mock_get_response.status_code = 200
    mock_get_response.json.return_value = {"status": "PENDING_DEPOSIT"}
    mock_httpx_client.get.return_value = mock_get_response

    request = SwapStatusRequest(
        tx_hash="",
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        deposit_address="empty_tx_hash_unique_addr_ghi012",
        deposit_memo=None,
        provider=SwapProviderEnum.NEAR_INTENTS,
        route_id="test-route-id",
    )

    result = await client.get_status(request)

    # Verify deposit submission was NOT called (empty tx_hash)
    mock_httpx_client.post.assert_not_called()

    assert result.status == SwapStatus.PENDING
    assert result.internal_status == "PENDING_DEPOSIT"


@pytest.mark.asyncio
async def test_get_status_pending_deposit_rate_limits_and_clears_cache(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    """Deposit submission is rate-limited and cache is cleared when status changes."""
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    mock_post_response = MagicMock()
    mock_post_response.status_code = 200
    mock_httpx_client.post.return_value = mock_post_response

    # Use a unique deposit address to avoid interference from other tests
    request = SwapStatusRequest(
        tx_hash="test_hash",
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        deposit_address="rate_limit_unique_addr_abc123",
        deposit_memo=None,
        provider=SwapProviderEnum.NEAR_INTENTS,
        route_id="test-route-id",
    )

    # Setup PENDING_DEPOSIT response
    mock_pending_response = MagicMock()
    mock_pending_response.status_code = 200
    mock_pending_response.json.return_value = {"status": "PENDING_DEPOSIT"}
    mock_httpx_client.get.return_value = mock_pending_response

    # First call should submit deposit
    await client.get_status(request)
    mock_httpx_client.post.assert_called_once_with(
        "https://1click.chaindefuser.com/v0/deposit/submit",
        json={"txHash": request.tx_hash, "depositAddress": request.deposit_address},
    )

    # Second call within 10s window should NOT submit deposit again (rate-limited)
    await client.get_status(request)
    assert mock_httpx_client.post.call_count == 1  # Still 1

    # Third call should also be rate-limited
    await client.get_status(request)
    assert mock_httpx_client.post.call_count == 1  # Still 1

    # Now simulate SUCCESS status - this should clear the cache
    mock_success_response = MagicMock()
    mock_success_response.status_code = 200
    mock_success_response.json.return_value = {"status": "SUCCESS"}
    mock_httpx_client.get.return_value = mock_success_response

    await client.get_status(request)
    assert mock_httpx_client.post.call_count == 1  # No submit for SUCCESS

    # Back to PENDING_DEPOSIT - should submit again since cache was cleared
    mock_httpx_client.get.return_value = mock_pending_response

    await client.get_status(request)
    assert mock_httpx_client.post.call_count == 2  # Now 2, cache was cleared


@pytest.mark.asyncio
async def test_route_price_impact_negative(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    """Test price impact calculation with negative impact (fees/slippage)."""
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": MOCK_QUOTE_REQUEST,
        "quote": {
            **MOCK_INDICATIVE_QUOTE,
            "amountInUsd": "100.0",
            "amountOutUsd": "95.0",  # 5% loss
        },
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="2037265",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    routes = await client.get_indicative_routes(request)

    # Verify price impact: (95.0 / 100.0 - 1) * 100 = -5.0
    assert len(routes) == 1
    result = routes[0]
    assert result.price_impact is not None
    assert result.price_impact == pytest.approx(-5.0, abs=0.01)


@pytest.mark.asyncio
async def test_get_status_error(client, mock_httpx_client, mock_supported_tokens_cache):
    supported_tokens = []
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock error response
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"message": "Swap not found"}
    mock_httpx_client.get.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="invalid_hash",
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        deposit_address="invalid_address",
        deposit_memo=None,
        provider=SwapProviderEnum.NEAR_INTENTS,
        route_id="test-route-id",
    )

    with pytest.raises(SwapError) as exc_info:
        await client.get_status(request)

    assert exc_info.value.message == "Swap not found"
    assert exc_info.value.kind == SwapErrorKind.UNKNOWN


@pytest.mark.asyncio
async def test_create_client_with_jwt(client):
    with patch("httpx.AsyncClient") as mock_client_class:
        client._create_client()
        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args[1]
        assert "Authorization" in call_kwargs["headers"]
        assert call_kwargs["headers"]["Authorization"] == "Bearer test_jwt_token"
        assert call_kwargs["timeout"] == 30.0


@pytest.mark.asyncio
async def test_create_client_without_jwt():
    with (
        patch("app.api.swap.providers.near_intents.client.settings") as mock_settings,
        patch("httpx.AsyncClient") as mock_client_class,
    ):
        mock_settings.NEAR_INTENTS_BASE_URL = "https://1click.chaindefuser.com"
        mock_settings.NEAR_INTENTS_JWT = None
        client = NearIntentsClient()

        client._create_client()
        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args[1]
        assert "Authorization" not in call_kwargs["headers"]
        assert call_kwargs["timeout"] == 30.0


# ============================================================================
# EXACT_OUTPUT Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_exact_output_indicative_route(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": MOCK_EXACT_OUTPUT_QUOTE_REQUEST,
        "quote": MOCK_EXACT_OUTPUT_INDICATIVE_QUOTE,
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="711",  # Desired output amount
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_OUTPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    routes = await client.get_indicative_routes(request)

    assert len(routes) == 1
    result = routes[0]

    # For EXACT_OUTPUT, source_amount is the min_amount_in (minimum required to proceed)
    assert result.source_amount == "2017265"

    # Destination amount is the exact requested amount
    assert result.destination_amount == "711"
    assert result.destination_amount_min == "711"

    # Indicative quote has no deposit address
    assert result.deposit_address is None
    assert result.transaction_params is None


@pytest.mark.asyncio
async def test_get_exact_output_firm_route_uses_max_amount_in(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": {**MOCK_EXACT_OUTPUT_QUOTE_REQUEST, "dry": False},
        "quote": MOCK_EXACT_OUTPUT_FIRM_QUOTE,
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="711",  # Desired output amount
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_OUTPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_firm_route(request)

    # For EXACT_OUTPUT, source_amount is min_amount_in (minimum required to proceed)
    assert result.source_amount == "2017265"
    assert result.destination_amount == "711"

    # Verify deposit address is set
    assert result.deposit_address == "9RdSjLtfFJLvj6CAR4w7H7tUbv2kvwkkrYZuoojKDBkE"

    # Verify transaction params use max_amount_in (2057265) not amount_in (2037265)
    # This ensures the swap will succeed; any excess is refunded
    assert result.transaction_params is not None
    assert result.transaction_params.solana is not None
    assert result.transaction_params.solana.spl_token_amount == "2057265"


@pytest.mark.asyncio
async def test_exact_input_route_uses_amount_in(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    supported_tokens = [
        USDC_ON_SOLANA_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": MOCK_QUOTE_REQUEST,
        "quote": MOCK_INDICATIVE_QUOTE,
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="2037265",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    routes = await client.get_indicative_routes(request)

    assert len(routes) == 1
    result = routes[0]

    # For EXACT_INPUT, source_amount is the amount_in from the quote
    assert result.source_amount == "2037265"


@pytest.mark.asyncio
async def test_near_intents_includes_slippage_percentage_in_route(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
):
    """Test that NEAR Intents includes slippage_percentage in the route response."""
    supported_tokens = [USDC_ON_SOLANA_TOKEN_INFO, BTC_TOKEN_INFO]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": MOCK_QUOTE_REQUEST,
        "quote": MOCK_INDICATIVE_QUOTE,
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapQuoteRequest(
        source_coin=Chain.SOLANA.coin,
        source_chain_id=Chain.SOLANA.chain_id,
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="2037265",
        slippage_percentage="1.5",  # Test with a specific value
        swap_type=SwapType.EXACT_INPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    routes = await client.get_indicative_routes(request)

    assert len(routes) == 1
    result = routes[0]
    # Verify slippage_percentage is included in the route response
    assert result.slippage_percentage == "1.5"
