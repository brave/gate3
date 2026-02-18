from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.common.models import Coin
from app.api.swap.models import (
    SwapError,
    SwapErrorKind,
    SwapProviderEnum,
    SwapRoute,
    SwapRouteStep,
    SwapStepToken,
    SwapTool,
)
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
        requires_token_allowance=False,
        requires_firm_route=True,
        slippage_percentage="0.5",
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
                        "percent": None,
                        "tool": {"name": "NEAR Intents", "logo": None},
                    }
                ],
                "sourceAmount": "1000000",
                "destinationAmount": "3500",
                "destinationAmountMin": "3450",
                "estimatedTime": None,
                "priceImpact": None,
                "networkFee": None,
                "gasless": False,
                "depositAddress": None,
                "depositMemo": None,
                "expiresAt": None,
                "transactionParams": None,
                "requiresTokenAllowance": False,
                "requiresFirmRoute": True,
                "slippagePercentage": "0.5",
            }
        ]
    }


def test_indicative_quote_defaults_slippage_for_non_auto_slippage_providers(
    mock_get_provider_client_for_request,
    mock_provider_client,
    mock_token_manager,
):
    """Test that slippage defaults to 0.5% for providers without auto slippage support."""
    # Setup mock provider with no auto slippage support
    mock_provider_client.has_auto_slippage_support = False
    mock_provider_client.get_indicative_routes = AsyncMock(
        return_value=[create_mock_route()]
    )
    mock_get_provider_client_for_request.return_value = mock_provider_client

    # Make request without slippage_percentage, but with a specific provider
    request_data = MOCK_REQUEST_DATA.copy()
    request_data.pop("slippagePercentage", None)
    request_data["provider"] = "NEAR_INTENTS"

    response = client.post("/api/swap/v1/quote/indicative", json=request_data)

    assert response.status_code == 200

    # Verify that provider's get_indicative_routes was called
    mock_provider_client.get_indicative_routes.assert_called_once()

    # Get the request that was passed to the provider
    call_args = mock_provider_client.get_indicative_routes.call_args
    request_arg = call_args[0][0]

    # Verify slippage was defaulted to 0.5%
    assert request_arg.slippage_percentage == "0.5"


def test_firm_quote_defaults_slippage_for_non_auto_slippage_providers(
    mock_get_provider_client_for_request,
    mock_provider_client,
    mock_token_manager,
):
    """Test that slippage defaults to 0.5% for providers without auto slippage support."""
    # Setup mock provider with no auto slippage support
    mock_provider_client.has_auto_slippage_support = False
    mock_provider_client.get_firm_route = AsyncMock(return_value=create_mock_route())
    mock_get_provider_client_for_request.return_value = mock_provider_client

    # Make request without slippage_percentage, but with a specific provider
    request_data = MOCK_REQUEST_DATA.copy()
    request_data.pop("slippagePercentage", None)
    request_data["provider"] = "NEAR_INTENTS"

    response = client.post("/api/swap/v1/quote/firm", json=request_data)

    assert response.status_code == 200

    # Verify that provider's get_firm_route was called
    mock_provider_client.get_firm_route.assert_called_once()

    # Get the request that was passed to the provider
    call_args = mock_provider_client.get_firm_route.call_args
    request_arg = call_args[0][0]

    # Verify slippage was defaulted to 0.5%
    assert request_arg.slippage_percentage == "0.5"


def test_indicative_quote_does_not_default_slippage_for_auto_slippage_providers(
    mock_get_provider_client_for_request,
    mock_provider_client,
    mock_token_manager,
):
    """Test that slippage is not defaulted for providers with auto slippage support."""
    # Setup mock provider with auto slippage support
    mock_provider_client.has_auto_slippage_support = True
    mock_provider_client.get_indicative_routes = AsyncMock(
        return_value=[create_mock_route()]
    )
    mock_get_provider_client_for_request.return_value = mock_provider_client

    # Make request without slippage_percentage, but with a specific provider
    request_data = MOCK_REQUEST_DATA.copy()
    request_data.pop("slippagePercentage", None)
    request_data["provider"] = "JUPITER"  # Jupiter supports auto slippage

    response = client.post("/api/swap/v1/quote/indicative", json=request_data)

    assert response.status_code == 200

    # Verify that provider's get_indicative_routes was called
    mock_provider_client.get_indicative_routes.assert_called_once()

    # Get the request that was passed to the provider
    call_args = mock_provider_client.get_indicative_routes.call_args
    request_arg = call_args[0][0]

    # Verify slippage was NOT defaulted (remains None)
    assert request_arg.slippage_percentage is None
