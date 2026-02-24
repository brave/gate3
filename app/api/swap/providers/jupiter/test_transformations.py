from unittest.mock import AsyncMock

import pytest

from app.api.common.models import Chain
from app.api.swap.models import (
    SwapError,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapType,
)
from app.api.tokens.manager import TokenManager

from .mocks import (
    MOCK_JUPITER_ORDER_RESPONSE,
    SOL_TOKEN_INFO,
    USDC_ON_SOLANA_TOKEN_INFO,
)
from .models import JupiterOrderResponse
from .transformations import from_jupiter_order_to_route


@pytest.fixture
def swap_request():
    return SwapQuoteRequest(
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


@pytest.fixture
def token_manager():
    manager = AsyncMock(spec=TokenManager)

    def side_effect(coin, chain_id, address):
        if address == "So11111111111111111111111111111111111111112" or address is None:
            return SOL_TOKEN_INFO
        if address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
            return USDC_ON_SOLANA_TOKEN_INFO
        return None

    manager.get = AsyncMock(side_effect=side_effect)
    return manager


def _jupiter_response(**overrides) -> JupiterOrderResponse:
    return JupiterOrderResponse.model_validate(
        {**MOCK_JUPITER_ORDER_RESPONSE, **overrides}
    )


@pytest.mark.asyncio
async def test_raises_on_empty_taker(swap_request, token_manager):
    with pytest.raises(SwapError, match="missing taker address"):
        await from_jupiter_order_to_route(
            _jupiter_response(taker=""), swap_request, token_manager
        )


@pytest.mark.asyncio
async def test_raises_on_empty_refund_to(token_manager):
    swap_request = SwapQuoteRequest(
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
        refund_to="",
        provider=SwapProviderEnum.JUPITER,
    )
    with pytest.raises(SwapError, match="missing refund_to address"):
        await from_jupiter_order_to_route(
            _jupiter_response(), swap_request, token_manager
        )


@pytest.mark.asyncio
async def test_raises_on_empty_transaction_with_error(swap_request, token_manager):
    response = _jupiter_response(
        transaction="", errorCode=42, errorMessage="Insufficient funds"
    )
    with pytest.raises(SwapError, match="Insufficient funds"):
        await from_jupiter_order_to_route(response, swap_request, token_manager)


@pytest.mark.asyncio
async def test_raises_on_empty_transaction_with_error_code_only(
    swap_request, token_manager
):
    response = _jupiter_response(transaction="", errorCode=42, errorMessage=None)
    with pytest.raises(SwapError, match="Jupiter error code: 42"):
        await from_jupiter_order_to_route(response, swap_request, token_manager)


@pytest.mark.asyncio
async def test_empty_transaction_without_error_returns_no_params(
    swap_request, token_manager
):
    response = _jupiter_response(transaction="")
    route = await from_jupiter_order_to_route(response, swap_request, token_manager)
    assert route.transaction_params is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bps", [-1, 10_001])
async def test_invalid_slippage_bps(swap_request, token_manager, bps):
    with pytest.raises(SwapError, match="invalid slippage_bps"):
        await from_jupiter_order_to_route(
            _jupiter_response(slippageBps=bps), swap_request, token_manager
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bps", "expected"),
    [(0, "0.0"), (10_000, "100.0")],
)
async def test_valid_slippage_bps_boundary(swap_request, token_manager, bps, expected):
    route = await from_jupiter_order_to_route(
        _jupiter_response(slippageBps=bps), swap_request, token_manager
    )
    assert route.slippage_percentage == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("impact", [-1.5, 1.01])
async def test_invalid_price_impact(swap_request, token_manager, impact):
    with pytest.raises(SwapError, match="invalid price impact"):
        await from_jupiter_order_to_route(
            _jupiter_response(priceImpact=impact), swap_request, token_manager
        )


@pytest.mark.asyncio
async def test_none_price_impact(swap_request, token_manager):
    route = await from_jupiter_order_to_route(
        _jupiter_response(priceImpact=None), swap_request, token_manager
    )
    assert route.price_impact is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("impact", "expected"),
    [(-1.0, -100.0), (1.0, 100.0)],
)
async def test_valid_price_impact_boundary(
    swap_request, token_manager, impact, expected
):
    route = await from_jupiter_order_to_route(
        _jupiter_response(priceImpact=impact), swap_request, token_manager
    )
    assert route.price_impact == expected
