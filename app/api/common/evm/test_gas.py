"""Tests for EVM gas price estimation utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.api.common.models import Chain

from .gas import (
    NotEvmChainError,
    _gas_price_cache,
    estimate_gas_limit,
    get_eip1559_gas_fees,
    get_evm_gas_price,
    get_gas_price,
)

# Fixtures


@pytest.fixture(autouse=True)
def clear_gas_price_cache():
    """Clear the gas price cache before each test."""
    _gas_price_cache.clear()
    yield
    _gas_price_cache.clear()


@pytest.fixture
def mock_httpx_client():
    with patch("app.api.common.evm.gas.httpx.AsyncClient") as mock:
        mock_client = AsyncMock()
        mock.return_value.__aenter__.return_value = mock_client
        yield mock_client


# Tests for non-EVM chain validation (parameterized)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "func,chain",
    [
        (get_gas_price, Chain.SOLANA),
        (get_gas_price, Chain.BITCOIN),
        (get_eip1559_gas_fees, Chain.SOLANA),
        (get_eip1559_gas_fees, Chain.BITCOIN),
        (get_evm_gas_price, Chain.SOLANA),
        (get_evm_gas_price, Chain.BITCOIN),
    ],
)
async def test_raises_for_non_evm_chain(func, chain):
    """Should raise NotEvmChainError for non-EVM chains."""
    with pytest.raises(NotEvmChainError):
        await func(chain)


# Tests for missing API key (parameterized)


@pytest.mark.asyncio
@pytest.mark.parametrize("func", [get_gas_price, get_eip1559_gas_fees])
async def test_returns_none_without_api_key(func):
    """Should return None when API key is not configured."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = None
        result = await func(Chain.ETHEREUM)
        assert result is None


# Tests for get_gas_price


@pytest.mark.asyncio
async def test_get_gas_price_returns_wei(mock_httpx_client):
    """Should return gas price converted from hex to int."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-api-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": "0x3b9aca00",  # 1 gwei = 1_000_000_000 wei
        }
        mock_httpx_client.post.return_value = mock_response

        result = await get_gas_price(Chain.ETHEREUM)
        assert result == 1_000_000_000


@pytest.mark.asyncio
async def test_get_gas_price_none_on_rpc_error(mock_httpx_client):
    """Should return None and log warning on RPC error."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-api-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "server error"},
        }
        mock_httpx_client.post.return_value = mock_response

        result = await get_gas_price(Chain.ETHEREUM)
        assert result is None


@pytest.mark.asyncio
async def test_get_gas_price_none_on_http_error(mock_httpx_client):
    """Should return None on HTTP error."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-api-key"

        mock_httpx_client.post.side_effect = httpx.HTTPError("Connection failed")

        result = await get_gas_price(Chain.ETHEREUM)
        assert result is None


# Tests for get_eip1559_gas_fees


@pytest.mark.asyncio
async def test_get_eip1559_gas_fees_returns_components(mock_httpx_client):
    """Should return base fee, priority fee, and total."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-api-key"

        # Base fee: 0x3b9aca00 = 1 gwei
        # Priority fees (50th percentile): 0x5f5e100 = 0.1 gwei
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "baseFeePerGas": ["0x3b9aca00", "0x3b9aca00"],  # 1 gwei
                "reward": [
                    ["0x2faf080", "0x5f5e100", "0x8f0d180"],  # 25th, 50th, 75th
                    ["0x2faf080", "0x5f5e100", "0x8f0d180"],
                ],
            },
        }
        mock_httpx_client.post.return_value = mock_response

        result = await get_eip1559_gas_fees(Chain.ETHEREUM)

        assert result is not None
        assert result["base_fee"] == 1_000_000_000  # 1 gwei
        assert result["priority_fee"] == 100_000_000  # 0.1 gwei
        assert result["total"] == 1_100_000_000  # 1.1 gwei


@pytest.mark.asyncio
async def test_get_eip1559_gas_fees_none_without_base_fees(mock_httpx_client):
    """Should return None when baseFeePerGas is empty."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-api-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "baseFeePerGas": [],
                "reward": [],
            },
        }
        mock_httpx_client.post.return_value = mock_response

        result = await get_eip1559_gas_fees(Chain.ETHEREUM)
        assert result is None


@pytest.mark.asyncio
async def test_get_eip1559_gas_fees_handles_zero_priority_fee(mock_httpx_client):
    """Should handle case with no priority fee rewards."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-api-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "baseFeePerGas": ["0x3b9aca00"],
                "reward": [],  # No reward data
            },
        }
        mock_httpx_client.post.return_value = mock_response

        result = await get_eip1559_gas_fees(Chain.ETHEREUM)

        assert result is not None
        assert result["base_fee"] == 1_000_000_000
        assert result["priority_fee"] == 0
        assert result["total"] == 1_000_000_000


# Tests for get_evm_gas_price


@pytest.mark.asyncio
async def test_get_evm_gas_price_uses_eip1559_when_available():
    """Should prefer EIP-1559 fees when available."""
    with (
        patch(
            "app.api.common.evm.gas.get_eip1559_gas_fees",
            new_callable=AsyncMock,
        ) as mock_eip1559,
        patch(
            "app.api.common.evm.gas.get_gas_price",
            new_callable=AsyncMock,
        ) as mock_legacy,
    ):
        mock_eip1559.return_value = {
            "base_fee": 1_000_000_000,
            "priority_fee": 100_000_000,
            "total": 1_100_000_000,
        }

        result = await get_evm_gas_price(Chain.ETHEREUM)

        assert result == 1_100_000_000
        mock_eip1559.assert_called_once_with(Chain.ETHEREUM)
        mock_legacy.assert_not_called()


@pytest.mark.asyncio
async def test_get_evm_gas_price_falls_back_to_legacy():
    """Should fall back to legacy gas price when EIP-1559 unavailable."""
    with (
        patch(
            "app.api.common.evm.gas.get_eip1559_gas_fees",
            new_callable=AsyncMock,
        ) as mock_eip1559,
        patch(
            "app.api.common.evm.gas.get_gas_price",
            new_callable=AsyncMock,
        ) as mock_legacy,
    ):
        mock_eip1559.return_value = None
        mock_legacy.return_value = 2_000_000_000

        result = await get_evm_gas_price(Chain.ETHEREUM)

        assert result == 2_000_000_000
        mock_eip1559.assert_called_once_with(Chain.ETHEREUM)
        mock_legacy.assert_called_once_with(Chain.ETHEREUM)


@pytest.mark.asyncio
async def test_get_evm_gas_price_none_when_both_unavailable():
    """Should return None when both methods fail."""
    with (
        patch(
            "app.api.common.evm.gas.get_eip1559_gas_fees",
            new_callable=AsyncMock,
        ) as mock_eip1559,
        patch(
            "app.api.common.evm.gas.get_gas_price",
            new_callable=AsyncMock,
        ) as mock_legacy,
    ):
        mock_eip1559.return_value = None
        mock_legacy.return_value = None

        result = await get_evm_gas_price(Chain.ETHEREUM)

        assert result is None


@pytest.mark.asyncio
async def test_get_evm_gas_price_caches_result():
    """Should cache gas price and return cached value on subsequent calls."""
    with (
        patch(
            "app.api.common.evm.gas.get_eip1559_gas_fees",
            new_callable=AsyncMock,
        ) as mock_eip1559,
        patch(
            "app.api.common.evm.gas.get_gas_price",
            new_callable=AsyncMock,
        ),
    ):
        mock_eip1559.return_value = {
            "base_fee": 1_000_000_000,
            "priority_fee": 100_000_000,
            "total": 1_100_000_000,
        }

        # First call should fetch from API
        result1 = await get_evm_gas_price(Chain.ETHEREUM)
        assert result1 == 1_100_000_000
        assert mock_eip1559.call_count == 1

        # Second call should use cache
        result2 = await get_evm_gas_price(Chain.ETHEREUM)
        assert result2 == 1_100_000_000
        assert mock_eip1559.call_count == 1  # Still 1, not called again

        # Different chain should fetch from API
        mock_eip1559.return_value = {
            "base_fee": 500_000_000,
            "priority_fee": 50_000_000,
            "total": 550_000_000,
        }
        result3 = await get_evm_gas_price(Chain.ARBITRUM)
        assert result3 == 550_000_000
        assert mock_eip1559.call_count == 2  # Called for new chain


# Tests for estimate_gas_limit


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", [Chain.SOLANA, Chain.BITCOIN])
async def test_estimate_gas_limit_raises_for_non_evm_chain(chain):
    """Should raise NotEvmChainError for non-EVM chains."""
    with pytest.raises(NotEvmChainError):
        await estimate_gas_limit(
            chain=chain,
            from_address="0x1234567890123456789012345678901234567890",
            to="0x0987654321098765432109876543210987654321",
            value="0",
            data="0x",
        )


@pytest.mark.asyncio
async def test_estimate_gas_limit_returns_none_without_api_key():
    """Should return None when API key is not configured."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = None
        result = await estimate_gas_limit(
            chain=Chain.ETHEREUM,
            from_address="0x1234567890123456789012345678901234567890",
            to="0x0987654321098765432109876543210987654321",
            value="0",
            data="0x",
        )
        assert result is None


@pytest.mark.asyncio
async def test_estimate_gas_limit_none_on_rpc_error(mock_httpx_client):
    """Should return None and log warning on RPC error."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-api-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "execution reverted"},
        }
        mock_httpx_client.post.return_value = mock_response

        result = await estimate_gas_limit(
            chain=Chain.ETHEREUM,
            from_address="0x1234567890123456789012345678901234567890",
            to="0x0987654321098765432109876543210987654321",
            value="0",
            data="0x",
        )
        assert result is None


@pytest.mark.asyncio
async def test_estimate_gas_limit_none_on_http_error(mock_httpx_client):
    """Should return None on HTTP error."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-api-key"

        mock_httpx_client.post.side_effect = httpx.HTTPError("Connection failed")

        result = await estimate_gas_limit(
            chain=Chain.ETHEREUM,
            from_address="0x1234567890123456789012345678901234567890",
            to="0x0987654321098765432109876543210987654321",
            value="0",
            data="0x",
        )
        assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chain",
    [Chain.ETHEREUM, Chain.ARBITRUM, Chain.BASE, Chain.POLYGON],
)
async def test_estimate_gas_limit_works_for_various_evm_chains(
    mock_httpx_client, chain
):
    """Should work for various EVM chains."""
    with patch("app.api.common.evm.gas.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-api-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": "0xfde8",  # 65000
        }
        mock_httpx_client.post.return_value = mock_response

        result = await estimate_gas_limit(
            chain=chain,
            from_address="0x1234567890123456789012345678901234567890",
            to="0x0987654321098765432109876543210987654321",
            value="0",
            data="0xa9059cbb",  # transfer() selector
        )
        assert result == 65000
