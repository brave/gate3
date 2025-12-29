from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.common.models import Coin
from app.api.swap.models import (
    RoutePriority,
    SwapError,
    SwapErrorKind,
    SwapProviderEnum,
    SwapRoute,
    SwapRouteStep,
    SwapStepToken,
    SwapTool,
    SwapType,
)
from app.api.swap.utils import sort_routes
from app.main import app

client = TestClient(app)


@pytest.fixture
def mock_get_provider_client_for_request():
    with patch(
        "app.api.swap.routes.get_provider_client_for_request",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_get_all_indicative_routes():
    with patch(
        "app.api.swap.routes.get_all_indicative_routes",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_token_manager():
    with patch("app.api.swap.routes.TokenManager") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_provider_client():
    mock_client = AsyncMock()
    return mock_client


MOCK_REQUEST_DATA = {
    "sourceCoin": "SOL",
    "sourceChainId": "mainnet",
    "sourceTokenAddress": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "destinationCoin": "BTC",
    "destinationChainId": "mainnet",
    "destinationTokenAddress": None,
    "recipient": "bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
    "amount": "1000000",
    "slippagePercentage": "0.5",
    "swapType": "EXACT_INPUT",
    "refundTo": "8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
}


def create_mock_route(
    route_id: str = "test-route-1",
    source_amount: str = "1000000",
    destination_amount: str = "3500",
    estimated_time: int | None = None,
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
        has_post_submit_hook=True,
        requires_token_allowance=False,
        requires_firm_route=True,
    )


def test_indicative_quote_insufficient_liquidity_error(
    mock_get_all_indicative_routes,
):
    # Setup mock to raise SwapError with INSUFFICIENT_LIQUIDITY kind
    error = SwapError(
        message="Amount is too low for bridge, try at least 1264000",
        kind=SwapErrorKind.INSUFFICIENT_LIQUIDITY,
    )
    mock_get_all_indicative_routes.side_effect = error

    response = client.post(
        "/api/swap/v1/quote/indicative",
        json=MOCK_REQUEST_DATA,
    )

    assert response.status_code == 400
    error_data = response.json()
    assert error_data["message"] == "Amount is too low for bridge, try at least 1264000"
    assert error_data["kind"] == "INSUFFICIENT_LIQUIDITY"


def test_firm_quote_insufficient_liquidity_error(
    mock_get_provider_client_for_request,
    mock_provider_client,
    mock_token_manager,
):
    error = SwapError(
        message="Amount is too small for this swap",
        kind=SwapErrorKind.INSUFFICIENT_LIQUIDITY,
    )
    mock_provider_client.get_firm_route = AsyncMock(side_effect=error)
    mock_get_provider_client_for_request.return_value = mock_provider_client

    response = client.post("/api/swap/v1/quote/firm", json=MOCK_REQUEST_DATA)

    assert response.status_code == 400
    error_data = response.json()
    assert error_data["message"] == "Amount is too small for this swap"
    assert error_data["kind"] == "INSUFFICIENT_LIQUIDITY"


def test_indicative_quote_unknown_error(
    mock_get_all_indicative_routes,
):
    error = SwapError(
        message="Unexpected error occurred",
        kind=SwapErrorKind.UNKNOWN,
    )
    mock_get_all_indicative_routes.side_effect = error

    response = client.post(
        "/api/swap/v1/quote/indicative",
        json=MOCK_REQUEST_DATA,
    )

    assert response.status_code == 400
    error_data = response.json()
    assert error_data["message"] == "Unexpected error occurred"
    assert error_data["kind"] == "UNKNOWN"


def test_firm_quote_unknown_error(
    mock_get_provider_client_for_request,
    mock_provider_client,
    mock_token_manager,
):
    error = SwapError(
        message="An unexpected error happened",
        kind=SwapErrorKind.UNKNOWN,
    )
    mock_provider_client.get_firm_route = AsyncMock(side_effect=error)
    mock_get_provider_client_for_request.return_value = mock_provider_client

    response = client.post("/api/swap/v1/quote/firm", json=MOCK_REQUEST_DATA)

    assert response.status_code == 400
    error_data = response.json()
    assert error_data["message"] == "An unexpected error happened"
    assert error_data["kind"] == "UNKNOWN"


def test_indicative_quote_response(mock_get_all_indicative_routes):
    mock_get_all_indicative_routes.return_value = [create_mock_route()]

    response = client.post("/api/swap/v1/quote/indicative", json=MOCK_REQUEST_DATA)

    assert response.status_code == 200
    assert response.json() == {
        "routes": [
            {
                "id": "test-route-1",
                "provider": "NEAR_INTENTS",
                "steps": [
                    {
                        "sourceToken": {
                            "coin": "SOL",
                            "chainId": "0x65",
                            "contractAddress": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                            "symbol": "USDC",
                            "decimals": 6,
                            "logo": None,
                        },
                        "sourceAmount": "1000000",
                        "destinationToken": {
                            "coin": "BTC",
                            "chainId": "bitcoin_mainnet",
                            "contractAddress": None,
                            "symbol": "BTC",
                            "decimals": 8,
                            "logo": None,
                        },
                        "destinationAmount": "3500",
                        "tool": {"name": "NEAR Intents", "logo": None},
                    }
                ],
                "sourceAmount": "1000000",
                "destinationAmount": "3500",
                "destinationAmountMin": "3450",
                "estimatedTime": None,
                "priceImpact": None,
                "depositAddress": None,
                "depositMemo": None,
                "expiresAt": None,
                "transactionParams": None,
                "hasPostSubmitHook": True,
                "requiresTokenAllowance": False,
                "requiresFirmRoute": True,
            }
        ]
    }


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
