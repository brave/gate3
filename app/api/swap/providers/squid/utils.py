import uuid

from app.api.common.models import Chain, Coin

from ...models import SwapErrorKind
from .constants import SQUID_NATIVE_TOKEN_ADDRESS


def get_squid_chain_id_from_chain(chain: Chain) -> str | None:
    """Convert Chain object to Squid API chain ID format.

    For EVM chains, converts hex chain ID to decimal string.
    For Bitcoin, returns "bitcoin".
    For Solana, returns "solana-mainnet-beta".

    Args:
        chain: Chain object

    Returns:
        Squid chain ID
    """
    if chain.coin == Coin.ETH:
        try:
            decimal_id = int(chain.chain_id, 16)
            return str(decimal_id)
        except (ValueError, TypeError):
            return None
    elif chain == Chain.BITCOIN:
        return "bitcoin"
    elif chain == Chain.SOLANA:
        return "solana-mainnet-beta"

    return None


def get_chain_from_squid_chain_id(squid_chain_id: str) -> Chain | None:
    """Convert Squid chain ID to Chain enum."""
    if squid_chain_id == "bitcoin":
        return Chain.BITCOIN
    elif squid_chain_id == "solana-mainnet-beta":
        return Chain.SOLANA
    elif squid_chain_id.isdigit():
        evm_chain_id = hex(int(squid_chain_id))
        return Chain.get(Coin.ETH, evm_chain_id)

    return None


def get_squid_token_address(chain: Chain, token_address: str | None) -> str:
    if chain.coin == Coin.ETH and token_address is None:
        return SQUID_NATIVE_TOKEN_ADDRESS

    if chain == Chain.BITCOIN:
        return "satoshi"

    if chain == Chain.SOLANA and token_address is None:
        return SQUID_NATIVE_TOKEN_ADDRESS

    # For non-native tokens, return the address as-is
    # This handles ERC20, SPL tokens, etc.
    return token_address


def convert_squid_token_address(chain: Chain, token_address: str | None) -> str | None:
    if token_address is None:
        return None
    if (
        chain.coin == Coin.ETH
        and token_address.lower() == SQUID_NATIVE_TOKEN_ADDRESS.lower()
    ):
        return None

    if chain == Chain.BITCOIN and token_address == "satoshi":
        return None

    if (
        chain == Chain.SOLANA
        and token_address.lower() == SQUID_NATIVE_TOKEN_ADDRESS.lower()
    ):
        return None

    return token_address


def categorize_error(error_message: str | None) -> SwapErrorKind:
    """Categorize a Squid error message into a provider-agnostic error kind.

    Args:
        error_message: The error message from Squid API

    Returns:
        SwapErrorKind enum value
    """
    if not error_message:
        return SwapErrorKind.UNKNOWN

    error_lower = error_message.lower()

    # Insufficient liquidity errors
    if any(
        phrase in error_lower
        for phrase in [
            "insufficient liquidity",
            "not enough liquidity",
            "liquidity",
            "no route found",
            "amount too small",
            "amount too low",
        ]
    ):
        return SwapErrorKind.INSUFFICIENT_LIQUIDITY

    return SwapErrorKind.UNKNOWN


def generate_route_id() -> str:
    """Generate a unique route ID for Squid routes."""
    return f"squid_{uuid.uuid4().hex[:12]}"
