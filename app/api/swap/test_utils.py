from unittest.mock import AsyncMock, patch

import pytest

from app.api.common.models import Coin
from app.api.swap.models import (
    NetworkFee,
    RoutePriority,
    SwapError,
    SwapErrorKind,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapRouteStep,
    SwapStepToken,
    SwapTool,
    SwapType,
)
from app.api.swap.utils import get_all_indicative_routes, sort_routes


def create_mock_route(
    route_id: str = "test-route-1",
    source_amount: str = "1000000",
    destination_amount: str = "3500",
    estimated_time: int | None = None,
    network_fee: NetworkFee | None = None,
    gasless: bool = False,
):
    """Helper to create a mock SwapRoute for testing."""
    return SwapRoute(
        id=route_id,
        provider=SwapProviderEnum.NEAR_INTENTS,
        steps=[
            SwapRouteStep(
                source_token=SwapStepToken(
                    coin=Coin.SOL,
                    chain_id="0x65",
                    contract_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    symbol="USDC",
                    decimals=6,
                    logo=None,
                ),
                source_amount=source_amount,
                destination_token=SwapStepToken(
                    coin=Coin.BTC,
                    chain_id="bitcoin_mainnet",
                    contract_address=None,
                    symbol="BTC",
                    decimals=8,
                    logo=None,
                ),
                destination_amount=destination_amount,
                tool=SwapTool(name="NEAR Intents", logo=None),
            )
        ],
        source_amount=source_amount,
        destination_amount=destination_amount,
        destination_amount_min="3450",
        estimated_time=estimated_time,
        network_fee=network_fee,
        gasless=gasless,
        requires_token_allowance=False,
        requires_firm_route=True,
        slippage_percentage="0.5",
    )


def create_mock_request() -> SwapQuoteRequest:
    """Create a mock SwapQuoteRequest for testing."""
    return SwapQuoteRequest(
        source_coin=Coin.SOL,
        source_chain_id="0x65",
        source_token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        destination_coin=Coin.BTC,
        destination_chain_id="bitcoin_mainnet",
        destination_token_address=None,
        recipient="bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
        amount="1000000",
        slippage_percentage="0.5",
        swap_type=SwapType.EXACT_INPUT,
        refund_to="8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
        provider=SwapProviderEnum.AUTO,
    )


# =============================================================================
# Tests for sort_routes
# =============================================================================


def test_sort_routes_cheapest_exact_input():
    """CHEAPEST + EXACT_INPUT sorts by highest destination_amount."""
    routes = [
        create_mock_route("low", destination_amount="1000"),
        create_mock_route("high", destination_amount="5000"),
        create_mock_route("mid", destination_amount="3000"),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.CHEAPEST, SwapType.EXACT_INPUT)

    assert [r.id for r in sorted_routes] == ["high", "mid", "low"]


def test_sort_routes_cheapest_exact_output():
    """CHEAPEST + EXACT_OUTPUT sorts by lowest source_amount."""
    routes = [
        create_mock_route("expensive", source_amount="5000"),
        create_mock_route("cheap", source_amount="1000"),
        create_mock_route("mid", source_amount="3000"),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.CHEAPEST, SwapType.EXACT_OUTPUT)

    assert [r.id for r in sorted_routes] == ["cheap", "mid", "expensive"]


def test_sort_routes_fastest():
    """FASTEST priority sorts by estimated_time ascending, 0 is atomic (fastest), None last."""
    routes = [
        create_mock_route("slow", estimated_time=300),
        create_mock_route("no_time", estimated_time=None),
        create_mock_route("fast", estimated_time=60),
        create_mock_route("atomic", estimated_time=0),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.FASTEST)

    assert [r.id for r in sorted_routes] == ["atomic", "fast", "slow", "no_time"]


def test_sort_routes_cheapest_tiebreak_by_fastest():
    """When destination_amount ties, break by fastest estimated_time."""
    routes = [
        create_mock_route("slow", destination_amount="5000", estimated_time=300),
        create_mock_route("fast", destination_amount="5000", estimated_time=60),
        create_mock_route("no_time", destination_amount="5000", estimated_time=None),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.CHEAPEST, SwapType.EXACT_INPUT)

    assert [r.id for r in sorted_routes] == ["fast", "slow", "no_time"]


def test_sort_routes_fastest_tiebreak_by_cheapest():
    """When estimated_time ties, break by cheapest (highest output for EXACT_INPUT)."""
    routes = [
        create_mock_route("low_output", destination_amount="1000", estimated_time=60),
        create_mock_route("high_output", destination_amount="5000", estimated_time=60),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.FASTEST, SwapType.EXACT_INPUT)

    assert [r.id for r in sorted_routes] == ["high_output", "low_output"]


def test_sort_routes_cheapest_exact_input_tiebreak_by_network_fee():
    """When destination_amount ties, break by lowest network_fee."""
    routes = [
        create_mock_route(
            "high_fee",
            destination_amount="5000",
            network_fee=NetworkFee(amount="100000", decimals=18, symbol="ETH"),
        ),
        create_mock_route(
            "low_fee",
            destination_amount="5000",
            network_fee=NetworkFee(amount="10000", decimals=18, symbol="ETH"),
        ),
        create_mock_route(
            "no_fee",
            destination_amount="5000",
            network_fee=None,
        ),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.CHEAPEST, SwapType.EXACT_INPUT)

    # Lower fee is better, None sorts last
    assert [r.id for r in sorted_routes] == ["low_fee", "high_fee", "no_fee"]


def test_sort_routes_cheapest_exact_output_tiebreak_by_network_fee():
    """When source_amount ties, break by lowest network_fee."""
    routes = [
        create_mock_route(
            "high_fee",
            source_amount="1000",
            network_fee=NetworkFee(amount="50000", decimals=9, symbol="SOL"),
        ),
        create_mock_route(
            "low_fee",
            source_amount="1000",
            network_fee=NetworkFee(amount="5000", decimals=9, symbol="SOL"),
        ),
        create_mock_route(
            "no_fee",
            source_amount="1000",
            network_fee=None,
        ),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.CHEAPEST, SwapType.EXACT_OUTPUT)

    # Lower fee is better, None sorts last
    assert [r.id for r in sorted_routes] == ["low_fee", "high_fee", "no_fee"]


def test_sort_routes_cheapest_exact_input_amount_beats_fee():
    """Higher destination_amount beats lower network_fee for EXACT_INPUT."""
    routes = [
        create_mock_route(
            "high_output_high_fee",
            destination_amount="6000",
            network_fee=NetworkFee(amount="100000", decimals=18, symbol="ETH"),
        ),
        create_mock_route(
            "low_output_low_fee",
            destination_amount="5000",
            network_fee=NetworkFee(amount="10000", decimals=18, symbol="ETH"),
        ),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.CHEAPEST, SwapType.EXACT_INPUT)

    # Higher output is more important than lower fee
    assert [r.id for r in sorted_routes] == [
        "high_output_high_fee",
        "low_output_low_fee",
    ]


def test_sort_routes_cheapest_exact_output_amount_beats_fee():
    """Lower source_amount beats lower network_fee for EXACT_OUTPUT."""
    routes = [
        create_mock_route(
            "low_input_high_fee",
            source_amount="900",
            network_fee=NetworkFee(amount="100000", decimals=18, symbol="ETH"),
        ),
        create_mock_route(
            "high_input_low_fee",
            source_amount="1000",
            network_fee=NetworkFee(amount="10000", decimals=18, symbol="ETH"),
        ),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.CHEAPEST, SwapType.EXACT_OUTPUT)

    # Lower input is more important than lower fee
    assert [r.id for r in sorted_routes] == ["low_input_high_fee", "high_input_low_fee"]


def test_sort_routes_gasless_treated_as_zero_fee_exact_input():
    """Gasless routes with None network_fee are treated as zero fee for EXACT_INPUT."""
    routes = [
        create_mock_route(
            "with_fee",
            destination_amount="5000",
            network_fee=NetworkFee(amount="10000", decimals=18, symbol="ETH"),
        ),
        create_mock_route(
            "gasless",
            destination_amount="5000",
            network_fee=None,
            gasless=True,
        ),
        create_mock_route(
            "no_fee_info",
            destination_amount="5000",
            network_fee=None,
            gasless=False,
        ),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.CHEAPEST, SwapType.EXACT_INPUT)

    # Gasless (zero fee) should be best, then with_fee, then no_fee_info (sorts last)
    assert [r.id for r in sorted_routes] == ["gasless", "with_fee", "no_fee_info"]


def test_sort_routes_gasless_treated_as_zero_fee_exact_output():
    """Gasless routes with None network_fee are treated as zero fee for EXACT_OUTPUT."""
    routes = [
        create_mock_route(
            "with_fee",
            source_amount="1000",
            network_fee=NetworkFee(amount="5000", decimals=9, symbol="SOL"),
        ),
        create_mock_route(
            "gasless",
            source_amount="1000",
            network_fee=None,
            gasless=True,
        ),
        create_mock_route(
            "no_fee_info",
            source_amount="1000",
            network_fee=None,
            gasless=False,
        ),
    ]

    sorted_routes = sort_routes(routes, RoutePriority.CHEAPEST, SwapType.EXACT_OUTPUT)

    # Gasless (zero fee) should be best, then with_fee, then no_fee_info (sorts last)
    assert [r.id for r in sorted_routes] == ["gasless", "with_fee", "no_fee_info"]


# =============================================================================
# Tests for get_all_indicative_routes
# =============================================================================


@pytest.mark.asyncio
async def test_get_all_indicative_routes_success_with_routes():
    """When at least one client returns routes, return them successfully."""
    mock_client = AsyncMock()
    mock_client.provider_id = SwapProviderEnum.NEAR_INTENTS
    mock_client.get_indicative_routes = AsyncMock(return_value=[create_mock_route()])

    with patch(
        "app.api.swap.utils.get_supported_provider_clients",
        new_callable=AsyncMock,
        return_value=[mock_client],
    ):
        request = create_mock_request()
        routes = await get_all_indicative_routes(request, token_manager=None)

        assert len(routes) == 1
        assert routes[0].id == "test-route-1"


@pytest.mark.asyncio
async def test_get_all_indicative_routes_success_ignores_failed_clients():
    """When some clients fail but at least one succeeds, return routes without raising."""
    # Client 1: fails with exception
    failing_client = AsyncMock()
    failing_client.provider_id = SwapProviderEnum.NEAR_INTENTS
    failing_client.get_indicative_routes = AsyncMock(
        side_effect=SwapError("Provider failed", SwapErrorKind.UNKNOWN)
    )

    # Client 2: succeeds
    success_client = AsyncMock()
    success_client.provider_id = SwapProviderEnum.JUPITER
    success_client.get_indicative_routes = AsyncMock(
        return_value=[create_mock_route("success-route")]
    )

    with patch(
        "app.api.swap.utils.get_supported_provider_clients",
        new_callable=AsyncMock,
        return_value=[failing_client, success_client],
    ):
        request = create_mock_request()
        routes = await get_all_indicative_routes(request, token_manager=None)

        # Should succeed with routes from the working client
        assert len(routes) == 1
        assert routes[0].id == "success-route"


@pytest.mark.asyncio
async def test_get_all_indicative_routes_raises_first_exception_when_no_routes():
    """When no routes returned but exceptions occurred, raise the first exception."""
    first_error = SwapError(
        "First provider failed", SwapErrorKind.INSUFFICIENT_LIQUIDITY
    )
    second_error = SwapError("Second provider failed", SwapErrorKind.UNKNOWN)

    client1 = AsyncMock()
    client1.provider_id = SwapProviderEnum.NEAR_INTENTS
    client1.get_indicative_routes = AsyncMock(side_effect=first_error)

    client2 = AsyncMock()
    client2.provider_id = SwapProviderEnum.JUPITER
    client2.get_indicative_routes = AsyncMock(side_effect=second_error)

    with patch(
        "app.api.swap.utils.get_supported_provider_clients",
        new_callable=AsyncMock,
        return_value=[client1, client2],
    ):
        request = create_mock_request()

        with pytest.raises(SwapError) as exc_info:
            await get_all_indicative_routes(request, token_manager=None)

        # Should raise the first exception
        assert exc_info.value.message == "First provider failed"
        assert exc_info.value.kind == SwapErrorKind.INSUFFICIENT_LIQUIDITY


@pytest.mark.asyncio
async def test_get_all_indicative_routes_raises_value_error_when_no_clients():
    """When no clients support the swap, raise ValueError."""
    with patch(
        "app.api.swap.utils.get_supported_provider_clients",
        new_callable=AsyncMock,
        return_value=[],  # No clients support the swap
    ):
        request = create_mock_request()

        with pytest.raises(ValueError) as exc_info:
            await get_all_indicative_routes(request, token_manager=None)

        assert "No provider supports this swap" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_all_indicative_routes_raises_value_error_when_empty_routes_no_exceptions():
    """When clients return empty routes with no exceptions, raise ValueError."""
    mock_client = AsyncMock()
    mock_client.provider_id = SwapProviderEnum.NEAR_INTENTS
    mock_client.get_indicative_routes = AsyncMock(return_value=[])  # Empty routes

    with patch(
        "app.api.swap.utils.get_supported_provider_clients",
        new_callable=AsyncMock,
        return_value=[mock_client],
    ):
        request = create_mock_request()

        with pytest.raises(ValueError) as exc_info:
            await get_all_indicative_routes(request, token_manager=None)

        assert "No provider supports this swap" in str(exc_info.value)
