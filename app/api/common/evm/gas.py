"""Gas price estimation utilities for EVM chains using Alchemy."""

import logging

import httpx
from cachetools import TTLCache

from app.config import settings

from ..models import Chain, Coin

logger = logging.getLogger(__name__)

# Cache gas prices for 2 minutes per chain
_gas_price_cache: TTLCache[str, int] = TTLCache(maxsize=100, ttl=120)

# Alchemy RPC URL template
ALCHEMY_RPC_URL_TEMPLATE = "https://{network}.g.alchemy.com/v2/{api_key}"


class NotEvmChainError(ValueError):
    """Raised when a non-EVM chain is passed to an EVM-only function."""

    def __init__(self, chain: Chain):
        self.chain = chain
        super().__init__(f"Chain {chain} is not an EVM chain (coin={chain.coin})")


def _validate_evm_chain(chain: Chain) -> None:
    """Validate that the chain is an EVM chain.

    Args:
        chain: The chain to validate

    Raises:
        NotEvmChainError: If the chain is not an EVM chain
    """
    if chain.coin != Coin.ETH:
        raise NotEvmChainError(chain)


def _get_alchemy_rpc_url(chain: Chain) -> str | None:
    """Get Alchemy RPC URL for a given EVM chain.

    Args:
        chain: The EVM chain to get RPC URL for

    Returns:
        The Alchemy RPC URL or None if API key not configured

    Raises:
        NotEvmChainError: If the chain is not an EVM chain
    """
    _validate_evm_chain(chain)

    if not settings.ALCHEMY_API_KEY:
        return None

    return ALCHEMY_RPC_URL_TEMPLATE.format(
        network=chain.alchemy_id,
        api_key=settings.ALCHEMY_API_KEY,
    )


async def get_gas_price(chain: Chain) -> int | None:
    """Get current gas price for an EVM chain in wei.

    Uses Alchemy's eth_gasPrice RPC method.

    Args:
        chain: The EVM chain to get gas price for

    Returns:
        Gas price in wei, or None if unavailable

    Raises:
        NotEvmChainError: If the chain is not an EVM chain
    """
    rpc_url = _get_alchemy_rpc_url(chain)
    if not rpc_url:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_gasPrice",
                    "params": [],
                },
            )
            response.raise_for_status()
            data = response.json()

            if "result" in data:
                # Result is hex string like "0x3b9aca00"
                return int(data["result"], 16)

            if "error" in data:
                logger.warning(
                    f"Alchemy gas price error for {chain.alchemy_id}: {data['error']}"
                )

    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch gas price for {chain.alchemy_id}: {e}")
    except (ValueError, KeyError) as e:
        logger.warning(f"Failed to parse gas price for {chain.alchemy_id}: {e}")

    return None


async def get_eip1559_gas_fees(chain: Chain) -> dict | None:
    """Get EIP-1559 gas fees (base fee + priority fee) for an EVM chain.

    Uses Alchemy's eth_feeHistory RPC method.

    Args:
        chain: The EVM chain to get gas fees for

    Returns:
        Dict with 'base_fee', 'priority_fee', and 'total' in wei, or None if unavailable

    Raises:
        NotEvmChainError: If the chain is not an EVM chain
    """
    rpc_url = _get_alchemy_rpc_url(chain)
    if not rpc_url:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_feeHistory",
                    "params": [
                        "0x4",  # 4 blocks
                        "latest",
                        [25, 50, 75],  # Percentiles for priority fee
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()

            if "result" in data:
                result = data["result"]
                # Get the latest base fee
                base_fees = result.get("baseFeePerGas", [])
                if base_fees:
                    base_fee = int(base_fees[-1], 16)
                else:
                    return None

                # Get median priority fee from rewards (50th percentile)
                rewards = result.get("reward", [])
                priority_fees = []
                for block_rewards in rewards:
                    if len(block_rewards) >= 2:  # 50th percentile is index 1
                        priority_fees.append(int(block_rewards[1], 16))

                priority_fee = (
                    sum(priority_fees) // len(priority_fees) if priority_fees else 0
                )

                return {
                    "base_fee": base_fee,
                    "priority_fee": priority_fee,
                    "total": base_fee + priority_fee,
                }

            if "error" in data:
                logger.warning(
                    f"Alchemy fee history error for {chain.alchemy_id}: {data['error']}"
                )

    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch fee history for {chain.alchemy_id}: {e}")
    except (ValueError, KeyError) as e:
        logger.warning(f"Failed to parse fee history for {chain.alchemy_id}: {e}")

    return None


async def estimate_gas_limit(
    chain: Chain,
    from_address: str,
    to: str,
    value: str,
    data: str,
) -> int | None:
    """Estimate gas limit for an EVM transaction using eth_estimateGas RPC.

    Args:
        chain: The EVM chain to estimate gas for
        from_address: The sender address
        to: The recipient/contract address
        value: The value to send in wei (decimal string)
        data: The transaction data (hex string)

    Returns:
        Estimated gas limit as int, or None if estimation fails

    Raises:
        NotEvmChainError: If the chain is not an EVM chain
    """
    rpc_url = _get_alchemy_rpc_url(chain)
    if not rpc_url:
        return None

    # Convert decimal value string to hex format for RPC call
    value_hex = hex(int(value)) if value and value != "0" else "0x0"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_estimateGas",
                    "params": [
                        {
                            "from": from_address,
                            "to": to,
                            "value": value_hex,
                            "data": data,
                        }
                    ],
                },
            )
            response.raise_for_status()
            data_response = response.json()

            if "result" in data_response:
                # Result is hex string like "0x5208" (21000)
                return int(data_response["result"], 16)

            if "error" in data_response:
                logger.warning(
                    f"Alchemy gas estimation error for {chain.alchemy_id}: {data_response['error']}"
                )

    except httpx.HTTPError as e:
        logger.warning(f"Failed to estimate gas for {chain.alchemy_id}: {e}")
    except (ValueError, KeyError) as e:
        logger.warning(f"Failed to parse gas estimate for {chain.alchemy_id}: {e}")

    return None


async def get_evm_gas_price(chain: Chain) -> int | None:
    """Get current gas price for an EVM chain.

    Tries EIP-1559 first (base + priority fee), falls back to legacy gas price.
    Results are cached for 2 minutes per chain.

    Args:
        chain: The EVM chain

    Returns:
        Gas price in wei, or None if unavailable

    Raises:
        NotEvmChainError: If the chain is not an EVM chain
    """
    _validate_evm_chain(chain)

    # Check cache first
    cache_key = f"{chain.coin.value}:{chain.chain_id}"
    if cache_key in _gas_price_cache:
        return _gas_price_cache[cache_key]

    # Try EIP-1559 first
    eip1559_fees = await get_eip1559_gas_fees(chain)
    if eip1559_fees:
        gas_price = eip1559_fees["total"]
        _gas_price_cache[cache_key] = gas_price
        return gas_price

    # Fall back to legacy gas price
    gas_price = await get_gas_price(chain)
    if gas_price is not None:
        _gas_price_cache[cache_key] = gas_price
    return gas_price
