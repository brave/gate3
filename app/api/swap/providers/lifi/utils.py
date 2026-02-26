import uuid

from app.api.common.models import Chain, Coin

from ...models import SwapErrorKind
from .constants import (
    LIFI_BITCOIN_CHAIN_ID,
    LIFI_BTC_NATIVE_TOKEN_ADDRESS,
    LIFI_EVM_NATIVE_TOKEN_ADDRESS,
    LIFI_SOL_NATIVE_TOKEN_ADDRESS,
    LIFI_SOLANA_CHAIN_ID,
)
from .models import LifiError


def get_lifi_chain_id(chain: Chain) -> int | None:
    """Convert Chain to LI.FI's decimal chain ID.

    EVM chains: hex chain_id to decimal int.
    Solana: 1151111081099710.
    Bitcoin: 20000000000001.
    Others: None (unsupported).
    """
    if chain.coin == Coin.ETH:
        try:
            return int(chain.chain_id, 16)
        except ValueError, TypeError:
            return None
    elif chain == Chain.SOLANA:
        return LIFI_SOLANA_CHAIN_ID
    elif chain == Chain.BITCOIN:
        return LIFI_BITCOIN_CHAIN_ID

    return None


def get_chain_from_lifi_chain_id(lifi_chain_id: int) -> Chain | None:
    """Convert LI.FI decimal chain ID to Chain enum."""
    if lifi_chain_id == LIFI_SOLANA_CHAIN_ID:
        return Chain.SOLANA
    if lifi_chain_id == LIFI_BITCOIN_CHAIN_ID:
        return Chain.BITCOIN

    # EVM chains: decimal to hex
    evm_chain_id = hex(lifi_chain_id)
    return Chain.get(Coin.ETH, evm_chain_id)


def get_lifi_token_address(chain: Chain, token_address: str | None) -> str:
    """Convert None (native) to the appropriate native address per chain."""
    if token_address:
        return token_address

    if chain.coin == Coin.ETH:
        return LIFI_EVM_NATIVE_TOKEN_ADDRESS
    if chain == Chain.SOLANA:
        return LIFI_SOL_NATIVE_TOKEN_ADDRESS
    if chain == Chain.BITCOIN:
        return LIFI_BTC_NATIVE_TOKEN_ADDRESS

    return token_address or ""


def convert_lifi_token_address(chain: Chain, token_address: str) -> str | None:
    """Convert LI.FI native addresses back to None."""
    if (
        chain.coin == Coin.ETH
        and token_address.lower() == LIFI_EVM_NATIVE_TOKEN_ADDRESS.lower()
    ):
        return None
    if chain == Chain.SOLANA and token_address == LIFI_SOL_NATIVE_TOKEN_ADDRESS:
        return None
    if chain == Chain.BITCOIN and token_address == LIFI_BTC_NATIVE_TOKEN_ADDRESS:
        return None
    return token_address


_ERROR_CODE_MAPPING: dict[int, SwapErrorKind] = {
    1000: SwapErrorKind.UNKNOWN,  # DefaultError
    1001: SwapErrorKind.INVALID_REQUEST,  # FailedToBuildTransactionError
    1002: SwapErrorKind.INSUFFICIENT_LIQUIDITY,  # NoQuoteError
    1003: SwapErrorKind.INVALID_REQUEST,  # NotFoundError
    1004: SwapErrorKind.INVALID_REQUEST,  # NotProcessableError
    1005: SwapErrorKind.RATE_LIMIT_EXCEEDED,  # RateLimitError
    1006: SwapErrorKind.UNKNOWN,  # ServerError
    1007: SwapErrorKind.INVALID_REQUEST,  # SlippageError
    1008: SwapErrorKind.UNKNOWN,  # ThirdPartyError
    1009: SwapErrorKind.TIMEOUT,  # TimeoutError
    1010: SwapErrorKind.INVALID_REQUEST,  # UnauthorizedError
    1011: SwapErrorKind.INVALID_REQUEST,  # ValidationError
    1012: SwapErrorKind.UNKNOWN,  # RpcFailure
    1013: SwapErrorKind.INVALID_REQUEST,  # MalformedSchema
}


def categorize_error(error: LifiError) -> SwapErrorKind:
    """Map LI.FI error codes to SwapErrorKind.

    Ref: https://docs.li.fi/api-reference/error-codes
    """
    if error.code is None:
        return SwapErrorKind.UNKNOWN
    return _ERROR_CODE_MAPPING.get(error.code, SwapErrorKind.UNKNOWN)


def generate_route_id() -> str:
    return f"lifi_{uuid.uuid4().hex[:12]}"


def convert_lifi_slippage(slippage_pct: str | None) -> float | None:
    """Convert percentage string (e.g., '0.5' = 0.5%) to LI.FI decimal (0.005)."""
    if slippage_pct is None:
        return None
    try:
        return float(slippage_pct) / 100.0
    except ValueError, TypeError:
        return None
