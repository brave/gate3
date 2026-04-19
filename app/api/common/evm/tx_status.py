"""EVM transaction receipt lookup via Alchemy eth_getTransactionReceipt."""

import logging
from enum import Enum

import httpx

from app.core.http import create_http_client

from ..models import Chain
from .utils import get_alchemy_rpc_url

logger = logging.getLogger(__name__)


class EvmTxReceiptStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


async def get_evm_tx_receipt_status(chain: Chain, tx_hash: str) -> EvmTxReceiptStatus:
    """Resolve an EVM transaction's receipt status via Alchemy RPC.

    No receipt yet or any RPC/parse error -> PENDING (optimistic retry).
    receipt.status == "0x1" -> SUCCESS.
    receipt.status == "0x0" -> FAILED.
    """
    rpc_url = get_alchemy_rpc_url(chain)
    if not rpc_url:
        return EvmTxReceiptStatus.PENDING

    try:
        async with create_http_client() as client:
            response = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_getTransactionReceipt",
                    "params": [tx_hash],
                },
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                logger.warning(
                    f"Alchemy tx receipt error for {chain.alchemy_id}: {data['error']}"
                )
                return EvmTxReceiptStatus.PENDING

            receipt = data.get("result")
            if receipt is None:
                return EvmTxReceiptStatus.PENDING

            status_hex = receipt.get("status")
            if status_hex == "0x1":
                return EvmTxReceiptStatus.SUCCESS
            if status_hex == "0x0":
                return EvmTxReceiptStatus.FAILED

            return EvmTxReceiptStatus.PENDING

    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch tx receipt for {chain.alchemy_id}: {e}")
    except (ValueError, KeyError) as e:
        logger.warning(f"Failed to parse tx receipt for {chain.alchemy_id}: {e}")

    return EvmTxReceiptStatus.PENDING
