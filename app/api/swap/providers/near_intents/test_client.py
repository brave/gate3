from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.api.common.models import Chain, Coin, TokenInfo, TokenSource, TokenType
from app.api.swap.models import (
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapStatusRequest,
    SwapSupportRequest,
    SwapType,
)

from .client import NearIntentsClient


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
        "app.api.swap.providers.near_intents.client.SupportedTokensCache"
    ) as mock_cache:
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        yield mock_cache


# Mock token data
USDC_TOKEN_DATA = {
    "assetId": "nep141:sol-5ce3bf3a31af18be40ba30f721101b4341690186.omft.near",
    "decimals": 6,
    "blockchain": "sol",
    "symbol": "USDC",
    "contractAddress": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}
USDC_TOKEN_INFO = TokenInfo(
    coin=Chain.SOLANA.coin,
    chain_id=Chain.SOLANA.chain_id,
    address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    name="USDC",
    symbol="USDC",
    decimals=6,
    logo=None,
    sources=[TokenSource.NEAR_INTENTS],
    token_type=TokenType.UNKNOWN,
    near_intents_asset_id="nep141:sol-5ce3bf3a31af18be40ba30f721101b4341690186.omft.near",
)

BTC_TOKEN_DATA = {
    "assetId": "nep141:btc.omft.near",
    "decimals": 8,
    "blockchain": "btc",
    "symbol": "BTC",
    "contractAddress": None,
}
BTC_TOKEN_INFO = TokenInfo(
    coin=Chain.BITCOIN.coin,
    chain_id=Chain.BITCOIN.chain_id,
    address=None,
    name="BTC",
    symbol="BTC",
    decimals=8,
    logo=None,
    sources=[TokenSource.NEAR_INTENTS],
    token_type=TokenType.UNKNOWN,
    near_intents_asset_id="nep141:btc.omft.near",
)

MOCK_QUOTE_REQUEST = {
    "dry": True,
    "depositMode": "SIMPLE",
    "swapType": "EXACT_INPUT",
    "slippageTolerance": 50,
    "originAsset": "nep141:sol-5ce3bf3a31af18be40ba30f721101b4341690186.omft.near",
    "depositType": "ORIGIN_CHAIN",
    "destinationAsset": "nep141:btc.omft.near",
    "amount": "2037265",
    "refundTo": "8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
    "refundType": "ORIGIN_CHAIN",
    "recipient": "bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
    "recipientType": "DESTINATION_CHAIN",
    "deadline": "2025-12-11T13:48:50.883000Z",
    "referral": "brave",
    "quoteWaitingTimeMs": 0,
}

MOCK_FIRM_QUOTE = {
    "amountIn": "2037265",
    "amountInFormatted": "2.037265",
    "amountInUsd": "2.0373",
    "amountOut": "711",
    "amountOutFormatted": "0.00000711",
    "amountOutUsd": "0.6546",
    "minAmountOut": "707",
    "timeEstimate": 465,
    "depositAddress": "9RdSjLtfFJLvj6CAR4w7H7tUbv2kvwkkrYZuoojKDBkE",
    "depositMemo": None,
    "deadline": "2025-12-11T13:48:50.883000Z",
}

MOCK_INDICATIVE_QUOTE = {
    **MOCK_FIRM_QUOTE,
    "depositAddress": None,
    "deadline": None,
}


@pytest.mark.asyncio
async def test_get_supported_tokens_from_api(
    client, mock_httpx_client, mock_supported_tokens_cache
):
    # Mock API response
    mock_response = MagicMock()
    mock_response.json.return_value = [
        USDC_TOKEN_DATA,
        BTC_TOKEN_DATA,
    ]
    mock_response.raise_for_status.return_value = None
    mock_httpx_client.get.return_value = mock_response

    tokens = await client.get_supported_tokens()

    # Verify API was called
    mock_httpx_client.get.assert_called_once_with(
        "https://1click.chaindefuser.com/v0/tokens"
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
    client, mock_httpx_client, mock_supported_tokens_cache
):
    cached_tokens = [USDC_TOKEN_INFO]
    mock_supported_tokens_cache.get.return_value = cached_tokens

    tokens = await client.get_supported_tokens()

    # Verify cache was checked
    mock_supported_tokens_cache.get.assert_called_once_with(
        SwapProviderEnum.NEAR_INTENTS
    )

    # Verify API was NOT called
    mock_httpx_client.get.assert_not_called()

    # Verify cached tokens were returned
    assert tokens == cached_tokens


@pytest.mark.asyncio
async def test_get_supported_tokens_http_error(
    client, mock_httpx_client, mock_supported_tokens_cache
):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
    )
    mock_httpx_client.get.return_value = mock_response

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_supported_tokens()


@pytest.mark.asyncio
async def test_has_support_success(client, mock_supported_tokens_cache):
    supported_tokens = [
        USDC_TOKEN_INFO,
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
        USDC_TOKEN_INFO,
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

    with pytest.raises(ValueError, match="Invalid swap parameters"):
        client._handle_error_response(mock_response)


@pytest.mark.asyncio
async def test_get_indicative_quote_success(
    client, mock_httpx_client, mock_supported_tokens_cache
):
    # Mock supported tokens
    supported_tokens = [
        USDC_TOKEN_INFO,
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
        slippage_tolerance=50,
        swap_type=SwapType.EXACT_INPUT,
        sender="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_indicative_quote(request)

    # Verify API was called
    mock_httpx_client.post.assert_called_once()
    call_args = mock_httpx_client.post.call_args
    assert call_args[0][0] == "https://1click.chaindefuser.com/v0/quote"
    assert call_args[1]["json"]["dry"] is True

    # Verify response
    assert result.provider == SwapProviderEnum.NEAR_INTENTS
    assert result.quote.amount_in == "2037265"
    assert result.quote.amount_out == "711"
    assert (
        result.quote.deposit_address is None
    )  # Indicative quote has no deposit address

    # Verify price impact calculation
    # amountInUsd: 2.0373, amountOutUsd: 0.6546
    # price_impact = (0.6546 / 2.0373 - 1) * 100 ≈ -67.87
    assert result.quote.price_impact is not None
    assert result.quote.price_impact == pytest.approx(-67.87, abs=0.1)


@pytest.mark.asyncio
async def test_get_firm_quote_success(
    client, mock_httpx_client, mock_supported_tokens_cache
):
    # Mock supported tokens
    supported_tokens = [
        USDC_TOKEN_INFO,
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
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Chain.BITCOIN.coin,
        destination_chain_id=Chain.BITCOIN.chain_id,
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="2037265",
        slippage_tolerance=50,
        swap_type=SwapType.EXACT_INPUT,
        sender="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_firm_quote(request)

    # Verify API was called
    mock_httpx_client.post.assert_called_once()
    call_args = mock_httpx_client.post.call_args
    assert call_args[0][0] == "https://1click.chaindefuser.com/v0/quote"
    assert call_args[1]["json"]["dry"] is False

    # Verify response
    assert result.provider == SwapProviderEnum.NEAR_INTENTS
    assert result.quote.amount_in == "2037265"
    assert result.quote.amount_out == "711"
    assert (
        result.quote.deposit_address == "9RdSjLtfFJLvj6CAR4w7H7tUbv2kvwkkrYZuoojKDBkE"
    )
    assert result.quote.expires_at is not None

    # Verify price impact calculation
    # amountInUsd: 2.0373, amountOutUsd: 0.6546
    # price_impact = (0.6546 / 2.0373 - 1) * 100 ≈ -67.87
    assert result.quote.price_impact is not None
    assert result.quote.price_impact == pytest.approx(-67.87, abs=0.1)


@pytest.mark.asyncio
async def test_get_quote_error_response(
    client, mock_httpx_client, mock_supported_tokens_cache
):
    supported_tokens = [
        USDC_TOKEN_INFO,
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
        slippage_tolerance=50,
        swap_type=SwapType.EXACT_INPUT,
        sender="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    with pytest.raises(ValueError, match="Invalid swap parameters"):
        await client.get_indicative_quote(request)


@pytest.mark.asyncio
async def test_post_submit_hook_success(client, mock_httpx_client):
    # Mock API response with valid structure
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteResponse": {
            "quoteRequest": MOCK_QUOTE_REQUEST,
            "quote": MOCK_INDICATIVE_QUOTE,
        },
        "status": "PENDING",
        "updatedAt": "2025-12-11T13:48:50.883000Z",
        "swapDetails": {},
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="4jLC9UPQJUyEK9dbgTywQQHeJTngX54FjJ6ZLPb1BUspGX4ZZGrg3u4P5tjHGqzpuq1c73rD2QwhyFQETvPgWdm5",
        deposit_address="4Rqnz7SPU4EqSUravxbKTSBti4RNf1XGaqvBmnLfvH83",
        deposit_memo=None,
        provider=SwapProviderEnum.NEAR_INTENTS,
    )

    await client.post_submit_hook(request)

    # Verify API was called
    mock_httpx_client.post.assert_called_once()
    call_args = mock_httpx_client.post.call_args
    assert call_args[0][0] == "https://1click.chaindefuser.com/v0/deposit/submit"
    assert call_args[1]["json"]["txHash"] == request.tx_hash
    assert call_args[1]["json"]["depositAddress"] == request.deposit_address
    assert "memo" not in call_args[1]["json"]


@pytest.mark.asyncio
async def test_post_submit_hook_with_memo(client, mock_httpx_client):
    # Mock API response with valid structure
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteResponse": {
            "quoteRequest": MOCK_QUOTE_REQUEST,
            "quote": MOCK_INDICATIVE_QUOTE,
        },
        "status": "PENDING",
        "updatedAt": "2025-12-11T13:48:50.883000Z",
        "swapDetails": {},
    }
    mock_httpx_client.post.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="test_hash",
        deposit_address="test_address",
        deposit_memo="test_memo",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )

    await client.post_submit_hook(request)

    # Verify memo was included
    call_args = mock_httpx_client.post.call_args
    assert call_args[1]["json"]["memo"] == "test_memo"


@pytest.mark.asyncio
async def test_post_submit_hook_error(client, mock_httpx_client):
    # Mock error response
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"message": "Invalid transaction hash"}
    mock_httpx_client.post.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="invalid_hash",
        deposit_address="test_address",
        deposit_memo=None,
        provider=SwapProviderEnum.NEAR_INTENTS,
    )

    with pytest.raises(ValueError, match="Invalid transaction hash"):
        await client.post_submit_hook(request)


@pytest.mark.asyncio
async def test_get_status_success(
    client, mock_httpx_client, mock_supported_tokens_cache
):
    # Mock supported tokens
    supported_tokens = [
        USDC_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteResponse": {
            "quoteRequest": MOCK_QUOTE_REQUEST,
            "quote": MOCK_FIRM_QUOTE,
        },
        "status": "SUCCESS",
        "updatedAt": "2025-12-11T13:48:50.883000Z",
        "swapDetails": {
            "amountIn": "2005138",
            "amountInFormatted": "2.005138",
            "amountInUsd": "2.0049",
            "amountOut": "711",
            "amountOutFormatted": "0.0000071",
            "amountOutUsd": "0.6433",
            "refundedAmount": "0",
            "refundedAmountFormatted": "0",
            "destinationChainTxHashes": [
                {
                    "hash": "ab7da53a8119097af975eee2c8ac09e035d549c605cfa712696267267a19414f",
                    "explorerUrl": "",
                }
            ],
        },
    }
    mock_httpx_client.get.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="4jLC9UPQJUyEK9dbgTywQQHeJTngX54FjJ6ZLPb1BUspGX4ZZGrg3u4P5tjHGqzpuq1c73rD2QwhyFQETvPgWdm5",
        deposit_address="4Rqnz7SPU4EqSUravxbKTSBti4RNf1XGaqvBmnLfvH83",
        deposit_memo=None,
        provider=SwapProviderEnum.NEAR_INTENTS,
    )

    result = await client.get_status(request)

    # Verify API was called
    mock_httpx_client.get.assert_called_once()
    call_args = mock_httpx_client.get.call_args
    assert call_args[0][0] == "https://1click.chaindefuser.com/v0/status"
    assert call_args[1]["params"]["depositAddress"] == request.deposit_address

    # Verify response
    assert result.status.value == "SUCCESS"
    assert result.provider == SwapProviderEnum.NEAR_INTENTS
    assert result.swap_details is not None
    assert result.swap_details.amount_in == "2005138"
    assert result.swap_details.amount_out == "711"


@pytest.mark.asyncio
async def test_get_status_with_memo(
    client, mock_httpx_client, mock_supported_tokens_cache
):
    # Mock supported tokens to avoid API call
    supported_tokens = [
        USDC_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response with valid structure (all required fields)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteResponse": {
            "quoteRequest": MOCK_QUOTE_REQUEST,
            "quote": MOCK_INDICATIVE_QUOTE,
        },
        "status": "PENDING",
        "updatedAt": "2025-12-11T13:48:50.883000Z",
        "swapDetails": {},
    }
    mock_httpx_client.get.return_value = mock_response

    request = SwapStatusRequest(
        tx_hash="test_hash",
        deposit_address="test_address",
        deposit_memo="test_memo",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )

    await client.get_status(request)

    # Verify memo was included in params
    call_args = mock_httpx_client.get.call_args
    assert call_args[1]["params"]["depositMemo"] == "test_memo"


@pytest.mark.asyncio
async def test_quote_price_impact_with_usd_values(
    client, mock_httpx_client, mock_supported_tokens_cache
):
    supported_tokens = [
        USDC_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response with USD values
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
        slippage_tolerance=50,
        swap_type=SwapType.EXACT_INPUT,
        sender="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_indicative_quote(request)

    # Verify price impact: (95.0 / 100.0 - 1) * 100 = -5.0
    assert result.quote.price_impact is not None
    assert result.quote.price_impact == pytest.approx(-5.0, abs=0.01)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "amount_in_usd,amount_out_usd,description",
    [
        (None, None, "missing USD values"),
        ("invalid", "95.0", "invalid amount_in_usd"),
        ("100.0", "invalid", "invalid amount_out_usd"),
        ("0", "95.0", "zero amount_in_usd"),
    ],
)
async def test_quote_price_impact_none_cases(
    client,
    mock_httpx_client,
    mock_supported_tokens_cache,
    amount_in_usd,
    amount_out_usd,
    description,
):
    supported_tokens = [
        USDC_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": MOCK_QUOTE_REQUEST,
        "quote": {
            **MOCK_INDICATIVE_QUOTE,
            "amountInUsd": amount_in_usd,
            "amountOutUsd": amount_out_usd,
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
        slippage_tolerance=50,
        swap_type=SwapType.EXACT_INPUT,
        sender="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_indicative_quote(request)

    assert result.quote.price_impact is None


@pytest.mark.asyncio
async def test_quote_price_impact_positive_impact(
    client, mock_httpx_client, mock_supported_tokens_cache
):
    supported_tokens = [
        USDC_TOKEN_INFO,
        BTC_TOKEN_INFO,
    ]
    mock_supported_tokens_cache.get.return_value = supported_tokens

    # Mock API response with positive price impact (unusual but possible)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quoteRequest": MOCK_QUOTE_REQUEST,
        "quote": {
            **MOCK_INDICATIVE_QUOTE,
            "amountInUsd": "100.0",
            "amountOutUsd": "105.0",  # 5% gain
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
        slippage_tolerance=50,
        swap_type=SwapType.EXACT_INPUT,
        sender="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.NEAR_INTENTS,
    )
    request.set_source_token(supported_tokens)
    request.set_destination_token(supported_tokens)

    result = await client.get_indicative_quote(request)

    # Verify price impact: (105.0 / 100.0 - 1) * 100 = 5.0
    assert result.quote.price_impact is not None
    assert result.quote.price_impact == pytest.approx(5.0, abs=0.01)


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
        deposit_address="invalid_address",
        deposit_memo=None,
        provider=SwapProviderEnum.NEAR_INTENTS,
    )

    with pytest.raises(ValueError, match="Swap not found"):
        await client.get_status(request)


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
