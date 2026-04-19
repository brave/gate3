"""Tests for EVM transaction status helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.api.common.models import Chain

from .tx_status import EvmTxReceiptStatus, get_evm_tx_receipt_status


@pytest.fixture
def mock_httpx_client():
    with patch("app.api.common.evm.tx_status.create_http_client") as mock:
        mock_client = AsyncMock()
        mock.return_value.__aenter__.return_value = mock_client
        yield mock_client


@pytest.mark.asyncio
async def test_returns_pending_without_api_key():
    with patch("app.api.common.evm.utils.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = None
        result = await get_evm_tx_receipt_status(Chain.ETHEREUM, "0xdeadbeef")
        assert result == EvmTxReceiptStatus.PENDING


@pytest.mark.asyncio
async def test_returns_success_on_status_0x1(mock_httpx_client):
    with patch("app.api.common.evm.utils.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"status": "0x1", "transactionHash": "0xabc"},
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = mock_response

        result = await get_evm_tx_receipt_status(Chain.ARBITRUM, "0xabc")
        assert result == EvmTxReceiptStatus.SUCCESS


@pytest.mark.asyncio
async def test_returns_failed_on_status_0x0(mock_httpx_client):
    with patch("app.api.common.evm.utils.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"status": "0x0", "transactionHash": "0xabc"},
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = mock_response

        result = await get_evm_tx_receipt_status(Chain.ETHEREUM, "0xabc")
        assert result == EvmTxReceiptStatus.FAILED


@pytest.mark.asyncio
async def test_returns_pending_when_receipt_null(mock_httpx_client):
    with patch("app.api.common.evm.utils.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": None}
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = mock_response

        result = await get_evm_tx_receipt_status(Chain.BASE, "0xabc")
        assert result == EvmTxReceiptStatus.PENDING


@pytest.mark.asyncio
async def test_returns_pending_on_rpc_error(mock_httpx_client):
    with patch("app.api.common.evm.utils.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "server error"},
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = mock_response

        result = await get_evm_tx_receipt_status(Chain.POLYGON, "0xabc")
        assert result == EvmTxReceiptStatus.PENDING


@pytest.mark.asyncio
async def test_returns_pending_on_http_error(mock_httpx_client):
    with patch("app.api.common.evm.utils.settings") as mock_settings:
        mock_settings.ALCHEMY_API_KEY = "test-key"

        mock_httpx_client.post.side_effect = httpx.HTTPError("network down")

        result = await get_evm_tx_receipt_status(Chain.OPTIMISM, "0xabc")
        assert result == EvmTxReceiptStatus.PENDING
