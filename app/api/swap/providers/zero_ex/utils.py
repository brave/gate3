import uuid

from app.api.common.models import Chain
from app.api.common.utils import is_address_equal

from ...models import SwapErrorKind
from .constants import ZERO_EX_NATIVE_TOKEN_ADDRESS, ZERO_EX_SUPPORTED_CHAINS
from .models import ZeroExError


def get_zero_ex_chain_id(chain: Chain | None) -> int | None:
    """Convert Chain to 0x's decimal chain ID.

    0x uses the standard EVM decimal chain ID. Only EVM chains in
    ZERO_EX_SUPPORTED_CHAINS are supported.
    """
    if chain is None or chain not in ZERO_EX_SUPPORTED_CHAINS:
        return None
    try:
        return int(chain.chain_id, 16)
    except ValueError, TypeError:
        return None


def get_zero_ex_token_address(token_address: str | None) -> str:
    """Convert None (native) to 0x's native token sentinel."""
    if token_address is None:
        return ZERO_EX_NATIVE_TOKEN_ADDRESS
    return token_address


def is_zero_ex_native_address(address: str) -> bool:
    return is_address_equal(address, ZERO_EX_NATIVE_TOKEN_ADDRESS)


def from_zero_ex_token_address(address: str | None) -> str | None:
    """Inverse of `get_zero_ex_token_address`: map the 0x native sentinel back to None.

    Use this when comparing user-supplied addresses, since callers may pass the
    native token as either None or the sentinel.
    """
    if address is None or is_zero_ex_native_address(address):
        return None
    return address


def convert_slippage_to_bps(slippage_pct: str | None) -> int | None:
    """Convert percentage string (e.g., '0.5' = 0.5%) to basis points (50).

    Returns None for unparseable, empty, or negative values.
    """
    if slippage_pct is None:
        return None
    stripped = slippage_pct.strip()
    if not stripped:
        return None
    try:
        bps = int(round(float(stripped) * 100))
    except ValueError, TypeError:
        return None
    if bps < 0:
        return None
    return bps


_ERROR_NAME_MAPPING: dict[str, SwapErrorKind] = {
    "VALIDATION_FAILED": SwapErrorKind.INVALID_REQUEST,
    "INPUT_INVALID": SwapErrorKind.INVALID_REQUEST,
    "TOKEN_NOT_SUPPORTED": SwapErrorKind.UNSUPPORTED_TOKENS,
    "INSUFFICIENT_LIQUIDITY": SwapErrorKind.INSUFFICIENT_LIQUIDITY,
    "SWAP_VALIDATION_FAILED": SwapErrorKind.INSUFFICIENT_LIQUIDITY,
    "UNAUTHORIZED": SwapErrorKind.INVALID_REQUEST,
    "RATE_LIMITED": SwapErrorKind.RATE_LIMIT_EXCEEDED,
    "GATEWAY_TIMEOUT": SwapErrorKind.TIMEOUT,
    "INTERNAL_SERVER_ERROR": SwapErrorKind.UNKNOWN,
}


def categorize_error(
    error: ZeroExError, status_code: int | None = None
) -> SwapErrorKind:
    """Map a 0x error payload to SwapErrorKind.

    Prefers the error `name` field, falling back to HTTP status code heuristics.
    """
    if error.name and error.name in _ERROR_NAME_MAPPING:
        return _ERROR_NAME_MAPPING[error.name]

    if status_code is not None:
        if status_code == 404:
            return SwapErrorKind.INSUFFICIENT_LIQUIDITY
        if status_code == 429:
            return SwapErrorKind.RATE_LIMIT_EXCEEDED
        if 400 <= status_code < 500:
            return SwapErrorKind.INVALID_REQUEST
        if 500 <= status_code < 600:
            return SwapErrorKind.UNKNOWN

    return SwapErrorKind.UNKNOWN


def generate_route_id() -> str:
    return f"zero_ex_{uuid.uuid4().hex[:12]}"
