from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.swap.models import (
    SwapError,
    SwapErrorKind,
)
from app.main import app

client = TestClient(app)


@pytest.fixture
def mock_get_or_select_provider_client():
    with patch(
        "app.api.swap.routes.get_or_select_provider_client", new_callable=AsyncMock
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
    "sender": "8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
}


def test_indicative_quote_insufficient_liquidity_error(
    mock_get_or_select_provider_client, mock_provider_client
):
    # Setup mock to raise SwapError with INSUFFICIENT_LIQUIDITY kind
    error = SwapError(
        message="Amount is too low for bridge, try at least 1264000",
        kind=SwapErrorKind.INSUFFICIENT_LIQUIDITY,
    )
    mock_provider_client.get_indicative_quote = AsyncMock(side_effect=error)
    mock_get_or_select_provider_client.return_value = mock_provider_client

    response = client.post("/api/swap/v1/quote/indicative", json=MOCK_REQUEST_DATA)

    assert response.status_code == 400
    error_data = response.json()
    assert error_data["message"] == "Amount is too low for bridge, try at least 1264000"
    assert error_data["kind"] == "INSUFFICIENT_LIQUIDITY"


def test_firm_quote_insufficient_liquidity_error(
    mock_get_or_select_provider_client, mock_provider_client, mock_token_manager
):
    error = SwapError(
        message="Amount is too small for this swap",
        kind=SwapErrorKind.INSUFFICIENT_LIQUIDITY,
    )
    mock_provider_client.get_firm_quote = AsyncMock(side_effect=error)
    mock_get_or_select_provider_client.return_value = mock_provider_client

    response = client.post("/api/swap/v1/quote/firm", json=MOCK_REQUEST_DATA)

    assert response.status_code == 400
    error_data = response.json()
    assert error_data["message"] == "Amount is too small for this swap"
    assert error_data["kind"] == "INSUFFICIENT_LIQUIDITY"


def test_indicative_quote_unknown_error(
    mock_get_or_select_provider_client, mock_provider_client
):
    error = SwapError(
        message="Unexpected error occurred",
        kind=SwapErrorKind.UNKNOWN,
    )
    mock_provider_client.get_indicative_quote = AsyncMock(side_effect=error)
    mock_get_or_select_provider_client.return_value = mock_provider_client

    response = client.post("/api/swap/v1/quote/indicative", json=MOCK_REQUEST_DATA)

    assert response.status_code == 400
    error_data = response.json()
    assert error_data["message"] == "Unexpected error occurred"
    assert error_data["kind"] == "UNKNOWN"


def test_firm_quote_unknown_error(
    mock_get_or_select_provider_client, mock_provider_client, mock_token_manager
):
    error = SwapError(
        message="An unexpected error happened",
        kind=SwapErrorKind.UNKNOWN,
    )
    mock_provider_client.get_firm_quote = AsyncMock(side_effect=error)
    mock_get_or_select_provider_client.return_value = mock_provider_client

    response = client.post("/api/swap/v1/quote/firm", json=MOCK_REQUEST_DATA)

    assert response.status_code == 400
    error_data = response.json()
    assert error_data["message"] == "An unexpected error happened"
    assert error_data["kind"] == "UNKNOWN"
